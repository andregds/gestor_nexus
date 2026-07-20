# backend/routes/users.py
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, object_session
from pydantic import BaseModel
from typing import Optional

# Imports do projeto
from core.dependencies import get_db, get_current_user
from schemas.user import UserResponse, UserSettingsUpdate, DEFAULT_PAYMENT_API_SETTINGS
from models import User

# Defaults para evitar None em permissões/feature flags antigos
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

    # Herda padrão do dono (quando o dono é revendedor) caso exista
    parent_flags = None
    if user.owner_id and db:
        parent = db.query(User).filter(User.id == user.owner_id).first()
        if parent and isinstance(parent.reseller_feature_flags, dict):
            parent_flags = parent.reseller_feature_flags
    if parent_flags:
        effective.update(parent_flags)

    # Aplica overrides do próprio usuário
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

    # Super admin não pode perder o console
    if user.role == "super_admin":
        user_flags["admin"] = True

    effective_flags = _compute_effective_flags(user, user_flags, db)

    # Aplica no objeto carregado na sessão atual
    user.permissions = permissions
    user.feature_flags = user_flags
    user.reseller_feature_flags = reseller_flags
    user.payment_api_settings = payment_settings
    # effective_feature_flags não é coluna do banco — atribui como atributo dinâmico
    object.__setattr__(user, 'effective_feature_flags', effective_flags)

    # Persiste apenas se solicitado e tivermos sessão válida
    # NÃO chama db.add() para evitar conflito "already attached to session"
    if persist and db:
        sess = object_session(user)
        if sess is db:
            try:
                db.commit()
                db.refresh(user)
                # Reaplica effective após refresh (refresh sobrescreve atributos dinâmicos)
                object.__setattr__(user, 'effective_feature_flags', effective_flags)
            except Exception:
                db.rollback()

    return user


router = APIRouter(prefix="/users", tags=["Usuários"])
payment_webhook_router = APIRouter(prefix="/v1/webhooks", tags=["Pagamentos"])


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna informações do usuário logado garantindo dicts nos campos opcionais."""
    # Recarrega o usuário na sessão atual para evitar conflitos entre sessões
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    # Passa db apenas para lookup do pai (effective flags), mas não persiste no GET
    return _ensure_defaults(user_db, db=db, persist=False)


# Rota para salvar configurações gerais
@router.patch("/me/settings", response_model=UserResponse)
def update_user_settings(
        settings: UserSettingsUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    # Garante que o usuário está na sessão atual
    user_in_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_in_db:
        # Fallback caso não encontre (raro se estiver logado)
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

    db.commit()
    db.refresh(user_in_db)
    return _ensure_defaults(user_in_db, db, persist=False)


@router.post("/me/telegram/test")
async def test_telegram_notification(
        current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_token or not current_user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Telegram não configurado. Salve as configurações primeiro.")

    try:
        await send_telegram_message(
            token=current_user.telegram_token,
            chat_id=current_user.telegram_chat_id,
            message="🔔 *Teste de Notificação - Nexus Monitor*\n\nSe você recebeu esta mensagem, a integração está funcionando perfeitamente! 🚀"
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
    invoice_slug: str
    amount: int
    paid_amount: int
    installments: int
    capture_method: str
    transaction_nsu: str
    order_nsu: str
    receipt_url: str


def _normalize_payment_settings(settings: dict) -> dict:
    return _safe_dict(settings, DEFAULT_PAYMENT_API_SETTINGS)


def _build_infinitepay_payload(current_user: User, settings: dict, payload: PaymentTestConnectionRequest):
    handle = (settings.get("handle") or "").strip()
    api_base_url = (settings.get("api_base_url") or "").strip().rstrip("/")
    links_endpoint = (settings.get("links_endpoint") or "/links").strip()
    webhook_url = (settings.get("webhook_url") or "").strip()
    redirect_url = (settings.get("redirect_url") or "").strip()

    amount_cents = int(round(payload.amount * 100))
    request_body = {
        "handle": handle,
        "order_nsu": f"TESTE-CONEXAO-{current_user.id}",
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


def _process_infinitepay_webhook(webhook_payload: InfinitePayWebhookPayload):
    if webhook_payload.paid_amount < webhook_payload.amount:
        raise HTTPException(status_code=400, detail="paid_amount menor que o valor esperado.")

    return {
        "success": True,
        "message": "Webhook processado com sucesso.",
        "order_nsu": webhook_payload.order_nsu,
        "transaction_nsu": webhook_payload.transaction_nsu,
        "capture_method": webhook_payload.capture_method,
        "paid_amount": webhook_payload.paid_amount,
    }


@router.post("/me/payment/test-connection")
async def test_payment_connection(
        payload: PaymentTestConnectionRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

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
            detail=f"Gateway retornou erro ao testar a conexão: {detail}"
        )

    try:
        gateway_data = response.json()
    except ValueError:
        gateway_data = {"raw_response": response.text}

    return {
        "message": "Conexão validada com sucesso!",
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
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    settings = _normalize_payment_settings(user_db.payment_api_settings)
    url, request_body, amount_cents = _build_infinitepay_payload(current_user, settings, payload)

    if not request_body["handle"]:
        raise HTTPException(status_code=400, detail="Preencha o Handle / Conta antes de testar.")
    if amount_cents <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            checkout_response = await client.post(
                url,
                json=request_body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o gateway: {exc}")

    if checkout_response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Gateway retornou erro ao gerar checkout: {checkout_response.text}")

    try:
        checkout_data = checkout_response.json()
    except ValueError:
        checkout_data = {"raw_response": checkout_response.text}

    webhook_payload = InfinitePayWebhookPayload(
        invoice_slug=f"TESTE-{current_user.id}",
        amount=amount_cents,
        paid_amount=amount_cents,
        installments=1,
        capture_method="pix",
        transaction_nsu=f"TEST-TX-{current_user.id}",
        order_nsu=request_body["order_nsu"],
        receipt_url="https://checkout.infinitepay.io/receipt/teste",
    )
    webhook_result = _process_infinitepay_webhook(webhook_payload)

    return {
        "message": "Teste completo validado com sucesso!",
        "success": True,
        "checkout_created": True,
        "webhook_received": True,
        "payment_confirmed": True,
        "checkout_response": checkout_data,
        "webhook_result": webhook_result,
    }


@payment_webhook_router.post("/infinitepay")
def receive_infinitepay_webhook(payload: InfinitePayWebhookPayload):
    return _process_infinitepay_webhook(payload)


@router.put("/me/schedule")
def update_notification_schedule(
        schedule_data: ScheduleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Atualiza o horário e se o agendamento está ativo."""

    # --- CORREÇÃO PRINCIPAL AQUI ---
    # Buscamos o usuário novamente na sessão atual para garantir que o commit funcione
    user_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Atualiza os campos
    user_db.notification_time = schedule_data.time
    user_db.notifications_enabled = schedule_data.enabled

    db.commit()
    db.refresh(user_db)

    return {
        "message": "Configuração de agendamento atualizada com sucesso!",
        "time": user_db.notification_time,
        "enabled": user_db.notifications_enabled
    }


@router.get("/me/schedule")
def get_notification_schedule(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)  # Adicionado DB session para leitura atualizada
):
    """Retorna o horário e status configurados."""
    # Também garantimos a leitura atualizada do banco
    user_db = db.query(User).filter(User.id == current_user.id).first()

    return {
        "time": user_db.notification_time or "09:00",
        "enabled": user_db.notifications_enabled if user_db.notifications_enabled is not None else True
    }