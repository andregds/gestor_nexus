# backend/routes/users.py
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, object_session
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timedelta
from typing import Optional
import json

# Imports do projeto
from core.dependencies import get_db, get_current_user
from schemas.user import UserResponse, UserSettingsUpdate, DEFAULT_PAYMENT_API_SETTINGS
from core.security import get_plan_duration_days
from models import User

# Defaults para evitar None em permisses/feature flags antigos
DEFAULT_PERMISSIONS = {
    "can_view_dashboard": True,
    "can_view_clients": True,
    "can_view_integrations": True,
    "can_view_settings": True,
}

DEFAULT_FEATURE_FLAGS = {
    "dashboard": True,
    "clients": True,
    "products": True,
    "whatsapp": True,
    "telegram": True,
    "settings": True,
    "resell": True,
    # somente super admin libera o console
    "admin": False,
}
DEFAULT_RESELLER_FEATURE_FLAGS = DEFAULT_FEATURE_FLAGS.copy()


def _safe_dict(value, default):
    return value if isinstance(value, dict) else default.copy()


def _compute_effective_flags(user: User, user_flags: dict, db: Optional[Session]):
    effective = DEFAULT_FEATURE_FLAGS.copy()

    # Herda padro do dono (quando o dono  revendedor) caso exista
    parent_flags = None
    if user.owner_id and db:
        parent = db.query(User).filter(User.id == user.owner_id).first()
        if parent and isinstance(parent.reseller_feature_flags, dict):
            parent_flags = parent.reseller_feature_flags
    if parent_flags:
        effective.update(parent_flags)

    # Aplica overrides do prprio usurio
    effective.update(user_flags or {})

    # Super admin sempre enxerga o console
    if user.role == "super_admin":
        effective["admin"] = True

    return effective


def _ensure_defaults(user: User, db: Optional[Session] = None, persist: bool = True):
    """Garante que permissions e feature_flags sejam dicts e gera effective_feature_flags."""
    if not user:
        return user

    # Normaliza todos os campos para dict
    permissions = _safe_dict(user.permissions, DEFAULT_PERMISSIONS)
    user_flags = _safe_dict(user.feature_flags, DEFAULT_FEATURE_FLAGS)
    reseller_flags = _safe_dict(user.reseller_feature_flags, DEFAULT_RESELLER_FEATURE_FLAGS)
    payment_settings = _safe_dict(user.payment_api_settings, DEFAULT_PAYMENT_API_SETTINGS)

    # Super admin no pode perder o console
    if user.role == "super_admin":
        user_flags["admin"] = True

    effective_flags = _compute_effective_flags(user, user_flags, db)

    # Aplica no objeto carregado na sesso atual
    user.permissions = permissions
    user.feature_flags = user_flags
    user.reseller_feature_flags = reseller_flags
    user.payment_api_settings = payment_settings
    # effective_feature_flags no  coluna do banco  atribui como atributo dinmico
    object.__setattr__(user, 'effective_feature_flags', effective_flags)

    # Persiste apenas se solicitado e tivermos sesso vlida
    # NO chama db.add() para evitar conflito "already attached to session"
    if persist and db:
        sess = object_session(user)
        if sess is db:
            try:
                db.commit()
                db.refresh(user)
                # Reaplica effective aps refresh (refresh sobrescreve atributos dinmicos)
                object.__setattr__(user, 'effective_feature_flags', effective_flags)
            except Exception:
                db.rollback()

    return user


router = APIRouter(prefix="/users", tags=["Usurios"])
payment_webhook_router = APIRouter(prefix="/v1/webhooks", tags=["Pagamentos"])


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna informaes do usurio logado garantindo dicts nos campos opcionais."""
    # Recarrega o usurio na sesso atual para evitar conflitos entre sesses
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usurio no encontrado")
    # Passa db apenas para lookup do pai (effective flags), mas no persiste no GET
    return _ensure_defaults(user_db, db=db, persist=False)


# Rota para salvar configuraes gerais
@router.patch("/me/settings", response_model=UserResponse)
def update_user_settings(
        settings: UserSettingsUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    # Garante que o usurio est na sesso atual
    user_in_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_in_db:
        # Fallback caso no encontre (raro se estiver logado)
        user_in_db = db.merge(current_user)

    if settings.whatsapp_number is not None:
        user_in_db.whatsapp_number = settings.whatsapp_number

    if settings.telegram_token is not None:
        user_in_db.telegram_token = settings.telegram_token
    if settings.telegram_chat_id is not None:
        user_in_db.telegram_chat_id = settings.telegram_chat_id

    if settings.notify_when_down is not None:
        user_in_db.notify_when_down = settings.notify_when_down
    if settings.notify_when_up is not None:
        user_in_db.notify_when_up = settings.notify_when_up
    if settings.notify_when_slow is not None:
        user_in_db.notify_when_slow = settings.notify_when_slow

    if settings.payment_api_settings is not None:
        payment_settings = _safe_dict(user_in_db.payment_api_settings, DEFAULT_PAYMENT_API_SETTINGS)
        payment_settings.update(settings.payment_api_settings)
        user_in_db.payment_api_settings = payment_settings
        flag_modified(user_in_db, "payment_api_settings")

    db.commit()
    db.refresh(user_in_db)
    return _ensure_defaults(user_in_db, db, persist=False)


@router.post("/me/telegram/test")
async def test_telegram_notification(
        current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_token or not current_user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Telegram no configurado. Salve as configuraes primeiro.")

    try:
        await send_telegram_message(
            token=current_user.telegram_token,
            chat_id=current_user.telegram_chat_id,
            message=" *Teste de Notificao - Nexus Monitor*\n\nSe voc recebeu esta mensagem, a integrao est funcionando perfeitamente! "
        )
        return {"message": "Mensagem de teste enviada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ROTAS DE AGENDAMENTO (CORRIGIDAS)
# ==========================================

class ScheduleUpdate(BaseModel):
    time: str  # Formato "HH:MM"
    enabled: bool = True  # Campo essencial para o switch funcionar


class PaymentTestConnectionRequest(BaseModel):
    product_name: str
    amount: float


class InfinitePayWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    invoice_slug: Optional[str] = None
    amount: Optional[int] = None
    paid_amount: Optional[int] = None
    installments: Optional[int] = None
    capture_method: Optional[str] = None
    transaction_nsu: Optional[str] = None
    order_nsu: Optional[str] = None
    receipt_url: Optional[str] = None
    status: Optional[str] = None


def _payload_to_dict(payload):
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return {}


def _normalize_payment_settings(settings: dict) -> dict:
    return _safe_dict(settings, DEFAULT_PAYMENT_API_SETTINGS)


def _build_infinitepay_payload(current_user: User, settings: dict, payload: PaymentTestConnectionRequest):
    handle = (settings.get("handle") or "").strip()
    api_base_url = (settings.get("api_base_url") or "").strip().rstrip("/")
    links_endpoint = (settings.get("links_endpoint") or "/links").strip()
    webhook_url = (settings.get("webhook_url") or "").strip()
    redirect_url = (settings.get("redirect_url") or "").strip()

    amount_cents = int(round(payload.amount * 100))
    
    # Gateway exige no mínimo 2 centavos (0.02)
    if amount_cents < 2:
        raise ValueError("O valor deve ser no minimo R$ 0.02 (2 centavos)")
    
    request_body = {
        "handle": handle,
        "order_nsu": f"TESTE-CONEXAO-{current_user.id}",
        "metadata": {
            "user_id": current_user.id,
            "user_email": current_user.email,
            "order_nsu": f"TESTE-CONEXAO-{current_user.id}",
        },
        "external_reference": f"TESTE-CONEXAO-{current_user.id}",
        "reference": f"TESTE-CONEXAO-{current_user.id}",
        "customer_email": current_user.email,
        "items": [
            {
                "description": payload.product_name.strip(),
                "quantity": 1,
                "price": amount_cents,
            }
        ],
        "customer": {
            "name": current_user.name,
            "email": current_user.email,
        },
    }

    if webhook_url:
        request_body["webhook_url"] = webhook_url
    if redirect_url:
        request_body["redirect_url"] = redirect_url

    url = f"{api_base_url}{links_endpoint if links_endpoint.startswith('/') else '/' + links_endpoint}"
    return url, request_body, amount_cents


def _extract_user_id_from_order(order_nsu: str) -> Optional[int]:
    if not order_nsu:
        return None
    parts = order_nsu.split("-")
    if len(parts) < 4:
        return None
    if parts[0] not in {"PLAN", "RENEW"}:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None


def _extract_customer_email(payload: dict) -> Optional[str]:
    candidates = [
        payload.get("customer_email"),
        payload.get("email"),
        payload.get("customerEmail"),
        payload.get("payer_email"),
        payload.get("buyer_email"),
    ]
    customer = payload.get("customer")
    if isinstance(customer, dict):
        candidates.extend([
            customer.get("email"),
            customer.get("customer_email"),
            customer.get("payer_email"),
        ])
    payer = payload.get("payer")
    if isinstance(payer, dict):
        candidates.extend([
            payer.get("email"),
            payer.get("payer_email"),
        ])
    for candidate in candidates:
        if candidate:
            return str(candidate).strip().lower()
    return None


def _find_user_for_webhook(db: Session, payload: dict) -> Optional[User]:
    """
    Busca usuario por multiplos identificadores em cascata:
    1. user_id direto no payload
    2. renewal_invoice_slug
    3. renewal_order_nsu
    4. order_nsu (extrai user_id)
    5. email do cliente
    """
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    
    # Tenta user_id direto (novo - para usuarios novos)
    user_id_direct = (
        payload.get("user_id")
        or payload.get("userId")
        or metadata.get("user_id")
    )
    if user_id_direct:
        try:
            user_db = db.query(User).filter(User.id == int(user_id_direct)).first()
            if user_db:
                print(f"[WEBHOOK] Usuario encontrado por user_id direto: {user_db.id}")
                return user_db
        except (TypeError, ValueError):
            pass
    
    # Tenta customer_id
    customer_id = (
        payload.get("customer_id")
        or payload.get("customerId")
        or metadata.get("customer_id")
    )
    if customer_id:
        try:
            customer_obj = payload.get("customer")
            if isinstance(customer_obj, dict) and customer_obj.get("id"):
                user_db = db.query(User).filter(User.id == int(customer_obj.get("id"))).first()
                if user_db:
                    print(f"[WEBHOOK] Usuario encontrado por customer.id: {user_db.id}")
                    return user_db
        except (TypeError, ValueError):
            pass
    
    # Tenta por invoice_slug
    invoice_slug = (
        payload.get("invoice_slug")
        or payload.get("invoiceSlug")
        or payload.get("slug")
        or payload.get("payment_slug")
        or payload.get("paymentSlug")
        or metadata.get("invoice_slug")
    )
    if invoice_slug:
        print(f"[WEBHOOK] Buscando por invoice_slug: {invoice_slug}")
        user_db = db.query(User).filter(User.renewal_invoice_slug == str(invoice_slug)).first()
        if user_db:
            print(f"[WEBHOOK] Usuario encontrado por invoice_slug: {user_db.id}")
            return user_db

    # Tenta por order_nsu (com format PLAN-ID-... ou RENEW-ID-...)
    order_nsu = (
        payload.get("order_nsu")
        or payload.get("orderNsu")
        or payload.get("external_reference")
        or payload.get("externalReference")
        or payload.get("reference")
        or metadata.get("order_nsu")
    )
    
    if order_nsu:
        print(f"[WEBHOOK] Buscando por order_nsu: {order_nsu}")
        user_id = _extract_user_id_from_order(str(order_nsu or ""))
        if user_id is not None:
            print(f"[WEBHOOK] Extraiu user_id do order_nsu: {user_id}")
            user_db = db.query(User).filter(User.id == user_id).first()
            if user_db:
                print(f"[WEBHOOK] Usuario encontrado por order_nsu/user_id: {user_db.id}")
                return user_db
        
        # Tenta encontrar por renewal_order_nsu (se ja foi pago antes)
        print(f"[WEBHOOK] Buscando por renewal_order_nsu: {order_nsu}")
        user_db = db.query(User).filter(User.renewal_order_nsu == str(order_nsu)).first()
        if user_db:
            print(f"[WEBHOOK] Usuario encontrado por renewal_order_nsu: {user_db.id}")
            return user_db

    # Tenta por email (ultimo recurso)
    customer_email = _extract_customer_email(payload)
    if customer_email:
        print(f"[WEBHOOK] Buscando por email: {customer_email}")
        user_db = db.query(User).filter(User.email == customer_email).first()
        if user_db:
            print(f"[WEBHOOK] Usuario encontrado por email: {user_db.id}")
            return user_db

    print(f"[WEBHOOK] ERRO: Nenhum usuario encontrado. Payload: {payload}")
    return None


def _process_infinitepay_webhook(webhook_payload: InfinitePayWebhookPayload, db: Session):
    """
    Processa webhook de pagamento confirmado.
    Renova automaticamente a conta do usuario.
    """
    payload_data = _payload_to_dict(webhook_payload)
    
    print(f"\n[WEBHOOK] ================================================")
    print(f"[WEBHOOK] NOVO WEBHOOK RECEBIDO")
    print(f"[WEBHOOK] ================================================")
    print(f"[WEBHOOK] Payload completo: {payload_data}")
    
    # Valida valores de pagamento
    amount_value = webhook_payload.amount
    paid_value = webhook_payload.paid_amount
    if amount_value is not None and paid_value is not None and paid_value < amount_value:
        print(f"[WEBHOOK] AVISO: paid_amount ({paid_value}) < amount ({amount_value})")
        raise HTTPException(status_code=400, detail="paid_amount menor que o valor esperado.")

    # Extrai status do pagamento
    status_value = str(
        payload_data.get("status")
        or payload_data.get("payment_status")
        or payload_data.get("event")
        or webhook_payload.status
        or ""
    ).strip().lower()
    
    print(f"[WEBHOOK] Status extraido: '{status_value}'")
    
    # Verifica se eh pagamento confirmado
    confirmacao_markers = ("approved", "paid", "confirm", "success", "completed")
    is_confirmed = any(marker in status_value for marker in confirmacao_markers)
    
    if status_value and not is_confirmed:
        print(f"[WEBHOOK] Nao eh confirmacao. Status: {status_value}")
        return {
            "success": True,
            "message": "Webhook recebido, mas sem confirmacao de pagamento.",
            "status": status_value,
        }

    print(f"[WEBHOOK] Pagamento CONFIRMADO!")
    
    # Busca o usuario no banco
    user_db = _find_user_for_webhook(db, payload_data)
    
    if not user_db:
        print(f"[WEBHOOK] ERRO: Usuario nao identificado!")
        print(f"[WEBHOOK] Tentativas: invoice_slug, order_nsu, email")
        print(f"[WEBHOOK] Payload usado: {payload_data}")
        return {
            "success": False,
            "message": "Pagamento confirmado, mas o usuario nao pode ser identificado.",
            "status": "user_not_found",
        }

    # Usuario encontrado! Processa renovacao
    print(f"\n[WEBHOOK] Pagamento confirmado para usuario: {user_db.id} ({user_db.email})")
    print(f"[WEBHOOK] ANTES da renovacao:")
    print(f"  - trial_expires_at: {user_db.trial_expires_at}")
    print(f"  - is_active: {user_db.is_active}")
    print(f"  - block_reason: {user_db.block_reason}")
    
    # Renova: calcula novos prazos
    trial_days = get_plan_duration_days(user_db)
    now = datetime.utcnow()
    
    # Se o usuario estava expirado, comeca do agora
    # Se ainda tinha tempo, estende a partir do vencimento anterior
    base_start = user_db.trial_expires_at if user_db.trial_expires_at and user_db.trial_expires_at > now else now
    
    user_db.trial_started_at = now
    user_db.trial_expires_at = base_start + timedelta(days=trial_days)
    user_db.is_active = True
    user_db.block_reason = None
    user_db.trial_expires_manually_set = False
    user_db.renewal_order_nsu = None
    user_db.renewal_order_created_at = None
    user_db.renewal_invoice_slug = None
    
    db.commit()
    db.refresh(user_db)
    
    print(f"[WEBHOOK] DEPOIS da renovacao:")
    print(f"  - trial_expires_at: {user_db.trial_expires_at}")
    print(f"  - is_active: {user_db.is_active}")
    print(f"  - block_reason: {user_db.block_reason}")
    print(f"[WEBHOOK] RENOVACAO CONCLUIDA COM SUCESSO!")
    print(f"[WEBHOOK] ================================================\n")
    
    return {
        "success": True,
        "message": "Webhook processado com sucesso. Usuario renovado.",
        "user_id": user_db.id,
        "user_email": user_db.email,
        "new_expiration": str(user_db.trial_expires_at),
        "is_active": user_db.is_active,
    }


# ==========================================
# ROTA PUBLICA DE WEBHOOK DO INFINITEPAY
# ==========================================
@payment_webhook_router.post("/infinitepay")
def receive_infinitepay_webhook(
        webhook_data: dict,
        db: Session = Depends(get_db)
):
    """
    Endpoint publico que recebe webhooks do InfinitePay.
    Nao requer autenticacao (public endpoint).
    Processa pagamentos confirmados e renova contas automaticamente.
    """
    print("\n" + "="*80)
    print("[WEBHOOK-RECEBIDO] WEBHOOK RECEBIDO DO INFINITEPAY!")
    print("="*80)
    print(f"[WEBHOOK-RECEBIDO] TIMESTAMP: {datetime.utcnow()}")
    print(f"[WEBHOOK-RECEBIDO] PAYLOAD COMPLETO:")
    print(json.dumps(webhook_data, indent=2, default=str))
    print("="*80)
    
    try:
        # Converte dict para InfinitePayWebhookPayload
        webhook_payload = InfinitePayWebhookPayload(**webhook_data)
        
        print("\n" + "="*80)
        print("[WEBHOOK-PROCESSANDO] PROCESSANDO WEBHOOK")
        print("="*80)
        
        # Processa o webhook
        result = _process_infinitepay_webhook(webhook_payload, db)
        
        print("\n" + "="*80)
        print("[WEBHOOK-RESULTADO] WEBHOOK PROCESSADO COM SUCESSO")
        print("="*80)
        print(json.dumps(result, indent=2, default=str))
        print("="*80 + "\n")
        
        return result
    
    except Exception as e:
        print("\n" + "="*80)
        print("[WEBHOOK-ERRO] ERRO AO PROCESSAR WEBHOOK")
        print("="*80)
        print(f"[WEBHOOK-ERRO] ERRO: {str(e)}")
        print(f"[WEBHOOK-ERRO] TIPO: {type(e).__name__}")
        import traceback
        print(f"[WEBHOOK-ERRO] TRACEBACK:")
        print(traceback.format_exc())
        print("="*80 + "\n")
        
        return {
            "success": False,
            "message": f"Erro ao processar webhook: {str(e)}",
        }


@router.post("/me/payment/test-connection")
async def test_payment_connection(
        payload: PaymentTestConnectionRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usurio no encontrado")

    settings = _normalize_payment_settings(user_db.payment_api_settings)

    url, request_body, amount_cents = _build_infinitepay_payload(current_user, settings, payload)

    if not request_body["handle"]:
        raise HTTPException(status_code=400, detail="Preencha o Handle / Conta antes de testar.")
    if not url:
        raise HTTPException(status_code=400, detail="Preencha a URL Base da API antes de testar.")
    if amount_cents <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json=request_body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o gateway: {exc}")

    if response.status_code >= 400:
        detail = response.text
        raise HTTPException(
            status_code=502,
            detail=f"Gateway retornou erro ao testar a conexo: {detail}"
        )

    try:
        gateway_data = response.json()
    except ValueError:
        gateway_data = {"raw_response": response.text}

    return {
        "message": "Conexo validada com sucesso!",
        "success": True,
        "integration_enabled": bool(settings.get("enabled")),
        "checkout_created": True,
        "webhook_received": False,
        "payment_confirmed": False,
        "gateway_response": gateway_data,
    }


@router.post("/me/payment/test-complete")
async def test_payment_complete(
        payload: PaymentTestConnectionRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    try:
        user_db = db.query(User).filter(User.id == current_user.id).first()
        if not user_db:
            raise HTTPException(status_code=404, detail="Usurio no encontrado")

        settings = _normalize_payment_settings(user_db.payment_api_settings)
        
        try:
            url, request_body, amount_cents = _build_infinitepay_payload(current_user, settings, payload)
        except Exception as e:
            print(f"[CHECKOUT-ERROR] Erro ao construir payload: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Erro ao construir payload: {str(e)}")

        if not request_body.get("handle"):
            raise HTTPException(status_code=400, detail="Preencha o Handle / Conta antes de testar.")
        if amount_cents <= 0:
            raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")

        checkout_response = None
        checkout_data = None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # LOG PRE-ENVIO
                print("\n" + "="*80)
                print("[CHECKOUT-REQUEST] PREPARANDO ENVIO AO GATEWAY")
                print("="*80)
                print(f"[CHECKOUT-REQUEST] URL DESTINO: {url}")
                print(f"[CHECKOUT-REQUEST] METODO: POST")
                print(f"[CHECKOUT-REQUEST] HEADERS: Content-Type: application/json")
                print(f"[CHECKOUT-REQUEST] BODY:")
                print(json.dumps(request_body, indent=2, default=str))
                print("="*80)
                
                checkout_response = await client.post(
                    url,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                )
                
                # LOG POS-RESPOSTA
                print("\n" + "="*80)
                print("[CHECKOUT-RESPONSE] RESPOSTA RECEBIDA DO GATEWAY")
                print("="*80)
                print(f"[CHECKOUT-RESPONSE] STATUS CODE: {checkout_response.status_code}")
                print(f"[CHECKOUT-RESPONSE] HEADERS:")
                for header_name, header_value in checkout_response.headers.items():
                    print(f"  {header_name}: {header_value}")
                print(f"[CHECKOUT-RESPONSE] BODY (RAW):")
                print(checkout_response.text)
                try:
                    response_json = checkout_response.json()
                    print(f"[CHECKOUT-RESPONSE] BODY (JSON):")
                    print(json.dumps(response_json, indent=2, default=str))
                except:
                    pass
                print("="*80 + "\n")
                
        except httpx.HTTPError as exc:
            print(f"\n[CHECKOUT-ERROR] ERRO AO COMUNICAR COM GATEWAY: {str(exc)}\n")
            raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o gateway: {exc}")
        except Exception as exc:
            print(f"\n[CHECKOUT-ERROR] ERRO INESPERADO: {str(exc)}\n")
            raise HTTPException(status_code=500, detail=f"Erro inesperado: {str(exc)}")

        if not checkout_response:
            raise HTTPException(status_code=500, detail="Nenhuma resposta do gateway")

        if checkout_response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Gateway retornou erro ao gerar checkout: {checkout_response.text}")

        try:
            checkout_data = checkout_response.json()
        except ValueError:
            checkout_data = {"raw_response": checkout_response.text}

        try:
            webhook_payload = InfinitePayWebhookPayload(
                invoice_slug=f"TESTE-{current_user.id}",
                amount=amount_cents,
                paid_amount=amount_cents,
                installments=1,
                capture_method="pix",
                transaction_nsu=f"TEST-TX-{current_user.id}",
                order_nsu=request_body["order_nsu"],
                receipt_url="https://checkout.infinitepay.io/receipt/teste",
                customer_email=current_user.email,
                status="approved",
            )
            webhook_result = _process_infinitepay_webhook(webhook_payload, db)
        except Exception as e:
            print(f"[WEBHOOK-ERROR] Erro ao processar webhook: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Erro ao processar webhook: {str(e)}")

        return {
            "message": "Teste completo validado com sucesso!",
            "success": True,
            "checkout_created": True,
            "webhook_received": True,
            "payment_confirmed": True,
            "checkout_response": checkout_data,
            "webhook_result": webhook_result,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n[TEST-ERROR] Erro no tratado em test_payment_complete: {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/me/payment/create-checkout")
def create_real_checkout(
        payload: PaymentTestConnectionRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Gera um checkout REAL para pagamento via InfinitePay.
    O usuario sera redirecionado para o gateway para fazer o pagamento.
    """
    try:
        print(f"\n[CREATE-REAL-CHECKOUT] Gerando checkout real para usuario {current_user.id}")
        
        from core.security import create_checkout_link_for_user
        
        checkout_url, gateway_response = create_checkout_link_for_user(current_user, db)
        
        print(f"[CREATE-REAL-CHECKOUT] Checkout gerado: {checkout_url[:80]}...")
        
        return {
            "success": True,
            "checkout_url": checkout_url,
            "url": checkout_url,
            "gateway_response": gateway_response,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CREATE-REAL-CHECKOUT] Erro: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Erro ao criar checkout: {str(e)}")


@router.post("/me/payment/sync")
def sync_payment(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Sincroniza o status de pagamento com o gateway.
    Util para renovacoes que nao chegaram via webhook.
    """
    try:
        print(f"\n[SYNC-PAYMENT] Sincronizando pagamento para usuario {current_user.id}")
        
        if not current_user.renewal_order_nsu and not current_user.renewal_invoice_slug:
            return {
                "success": False,
                "message": "Nenhuma renovacao pendente",
                "status": "no_renewal_pending",
            }
        
        from core.security import sync_user_payment_from_gateway
        
        result = sync_user_payment_from_gateway(current_user, db)
        
        if result:
            return {
                "success": True,
                "message": "Pagamento sincronizado e usuario renovado!",
                "user_id": current_user.id,
                "is_active": current_user.is_active,
                "trial_expires_at": str(current_user.trial_expires_at),
            }
        else:
            return {
                "success": False,
                "message": "Pagamento ainda nao confirmado no gateway",
                "status": "payment_not_confirmed",
            }
    
    except Exception as e:
        print(f"[SYNC-PAYMENT] Erro: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Erro ao sincronizar: {str(e)}")


@router.get("/admin/users/{user_id}/debug")
def debug_user_renewal_status(
        user_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """DEBUG: Mostra estado de renovao de um usurio"""
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Apenas Super Admin")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usurio no encontrado")
    
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "block_reason": user.block_reason,
        "selected_plan": user.selected_plan,
        "trial_started_at": user.trial_started_at,
        "trial_expires_at": user.trial_expires_at,
        "trial_expires_manually_set": user.trial_expires_manually_set,
        "renewal_order_nsu": user.renewal_order_nsu,
        "renewal_order_created_at": user.renewal_order_created_at,
        "renewal_invoice_slug": user.renewal_invoice_slug,
        "payment_api_settings": {
            "webhook_url": user.payment_api_settings.get("webhook_url") if user.payment_api_settings else None,
            "handle": user.payment_api_settings.get("handle") if user.payment_api_settings else None,
        } if user.payment_api_settings else None,
        "status_summary": {
            "status_atual": "ATIVO" if user.is_active else "INATIVO",
            "motivo_bloqueio": user.block_reason,
            "pode_renovar": user.renewal_order_nsu is not None or user.renewal_invoice_slug is not None,
            "renovao_manual": user.trial_expires_manually_set,
        }
    }


@router.post("/me/payment/test-webhook")
async def test_webhook_directly(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Simula um webhook de pagamento confirmado para testar a renovacao automatica.
    APENAS PARA TESTES - Nao usa gateway real.
    """
    print(f"[TEST-WEBHOOK] Iniciando teste de webhook para usuario {current_user.id} ({current_user.email})")
    
    # Busca o usuario novamente para ter renewal_order_nsu atualizado
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    
    print(f"[TEST-WEBHOOK] Dados do usuario:")
    print(f"  - renewal_order_nsu: {user_db.renewal_order_nsu}")
    print(f"  - renewal_invoice_slug: {user_db.renewal_invoice_slug}")
    print(f"  - email: {user_db.email}")
    
    # Cria um payload de teste realista
    # Usa o renewal_order_nsu real do usuario se existir, senao usa o email como fallback
    order_nsu_value = user_db.renewal_order_nsu or f"PLAN-{current_user.id}-{int(datetime.utcnow().timestamp())}"
    
    webhook_payload = InfinitePayWebhookPayload(
        invoice_slug=user_db.renewal_invoice_slug or f"TEST-INVOICE-{current_user.id}-{int(datetime.utcnow().timestamp())}",
        amount=4990,
        paid_amount=4990,
        installments=1,
        capture_method="pix",
        transaction_nsu=f"TEST-TX-{current_user.id}-{int(datetime.utcnow().timestamp())}",
        order_nsu=order_nsu_value,
        receipt_url="https://checkout.infinitepay.io/receipt/teste",
        status="approved",
    )
    
    print(f"[TEST-WEBHOOK] Payload para webhook:")
    print(f"  - order_nsu: {webhook_payload.order_nsu}")
    print(f"  - invoice_slug: {webhook_payload.invoice_slug}")
    print(f"  - status: {webhook_payload.status}")
    
    # Processa como webhook real
    webhook_result = _process_infinitepay_webhook(webhook_payload, db)
    
    print(f"[TEST-WEBHOOK] Resultado do webhook: {webhook_result}")
    
    # Recarrega o usuario para verificar se foi atualizado
    db.refresh(user_db)
    print(f"[TEST-WEBHOOK] Usuario apos webhook:")
    print(f"  - is_active: {user_db.is_active}")
    print(f"  - trial_expires_at: {user_db.trial_expires_at}")
    print(f"  - block_reason: {user_db.block_reason}")
    
    return {
        "message": "Webhook de teste processado com sucesso! Verifique os logs do backend.",
        "success": True,
        "webhook_result": webhook_result,
        "test_user_id": current_user.id,
        "test_email": current_user.email,
        "debug": {
            "renewal_order_nsu": user_db.renewal_order_nsu,
            "renewal_invoice_slug": user_db.renewal_invoice_slug,
            "user_is_active": user_db.is_active,
            "user_expires_at": str(user_db.trial_expires_at),
        }
    }


@router.put("/me/schedule")
def update_notification_schedule(
        schedule_data: ScheduleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Atualiza o horrio e se o agendamento est ativo."""

    # --- CORREO PRINCIPAL AQUI ---
    # Buscamos o usurio novamente na sesso atual para garantir que o commit funcione
    user_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usurio no encontrado")

    # Atualiza os campos
    user_db.notification_time = schedule_data.time
    user_db.notifications_enabled = schedule_data.enabled

    db.commit()
    db.refresh(user_db)

    return {
        "message": "Configurao de agendamento atualizada com sucesso!",
        "time": user_db.notification_time,
        "enabled": user_db.notifications_enabled
    }


@router.get("/me/schedule")
def get_notification_schedule(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)  # Adicionado DB session para leitura atualizada
):
    """Retorna o horrio e status configurados."""
    # Tambm garantimos a leitura atualizada do banco
    user_db = db.query(User).filter(User.id == current_user.id).first()

    return {
        "time": user_db.notification_time or "09:00",
        "enabled": user_db.notifications_enabled if user_db.notifications_enabled is not None else True
    }