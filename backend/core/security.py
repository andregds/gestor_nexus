# backend/core/security.py
from datetime import datetime, timedelta
from typing import Optional
import httpx
from uuid import uuid4
from jose import jwt
from passlib.context import CryptContext
import os
from types import SimpleNamespace
from dotenv import load_dotenv
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models import User
from schemas.user import DEFAULT_PAYMENT_API_SETTINGS
import json
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

try:
    import bcrypt as _bcrypt
    if not hasattr(_bcrypt, "__about__"):
        _bcrypt.__about__ = SimpleNamespace(__version__=getattr(_bcrypt, "__version__", "0"))
except Exception:
    pass

# Configurações de Segurança
# Em produção, certifique-se de ter SECRET_KEY no seu arquivo .env
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PLAN_DURATION_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "semiannual": 180,
    "yearly": 365,
}

PLAN_DEFAULT_PRICES = {
    "monthly": 49.90,
    "quarterly": 129.90,
    "semiannual": 229.90,
    "yearly": 399.90,
}

PLAN_LABEL_HINTS = {
    "mensal": "monthly",
    "trimestral": "quarterly",
    "semestral": "semiannual",
    "anual": "yearly",
}


def _normalize_payment_settings(settings):
    if isinstance(settings, dict):
        merged = DEFAULT_PAYMENT_API_SETTINGS.copy()
        merged.update(settings)
        return merged
    return DEFAULT_PAYMENT_API_SETTINGS.copy()


def _resolve_plan_key(user):
    raw_key = (getattr(user, "selected_plan", None) or "").strip().lower()
    if raw_key in PLAN_DURATION_DAYS:
        return raw_key

    raw_label = (getattr(user, "selected_plan_label", None) or "").strip().lower()
    for hint, key in PLAN_LABEL_HINTS.items():
        if hint in raw_label:
            return key

    return raw_key or "monthly"


def _deep_find_first_string(payload, target_keys):
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in target_keys or any(target in key_text for target in target_keys):
                if value:
                    return str(value).strip()
            found = _deep_find_first_string(value, target_keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _deep_find_first_string(item, target_keys)
            if found:
                return found
    return None


def get_renewal_order_nsu(user):
    return getattr(user, "renewal_order_nsu", None)


def ensure_renewal_order_nsu(user, db: Optional[Session] = None, force_new: bool = False):
    existing = get_renewal_order_nsu(user)
    if existing and not force_new:
        return existing

    token = f"RENEW-{user.id}-{_resolve_plan_key(user)}-{uuid4().hex[:10]}"
    user.renewal_order_nsu = token
    user.renewal_order_created_at = datetime.utcnow()
    if db:
        db.commit()
        db.refresh(user)
    return token


def get_plan_duration_days(user):
    return PLAN_DURATION_DAYS.get(_resolve_plan_key(user), 30)


def get_plan_price(user):
    price = getattr(user, "selected_plan_price", None)
    if price is not None:
        try:
            numeric_price = float(price)
            if numeric_price > 0:
                return numeric_price
        except (TypeError, ValueError):
            pass

    return PLAN_DEFAULT_PRICES.get(_resolve_plan_key(user), 0.0)


def build_checkout_payload(user, order_nsu: Optional[str] = None):
    settings = _normalize_payment_settings(getattr(user, "payment_api_settings", None))
    
    # DEBUG: Mostrar todas as settings
    print(f"\n[CHECKOUT-DEBUG] Settings completo:")
    print(json.dumps(settings, indent=2, default=str))
    
    handle = (settings.get("handle") or "").strip()
    api_base_url = (settings.get("api_base_url") or "").strip().rstrip("/")
    links_endpoint = (settings.get("links_endpoint") or "/links").strip()
    webhook_url = (settings.get("webhook_url") or "").strip()
    redirect_url = (settings.get("redirect_url") or "").strip()
    amount = get_plan_price(user)
    
    print(f"[CHECKOUT-DEBUG] webhook_url extraido: '{webhook_url}'")
    print(f"[CHECKOUT-DEBUG] webhook_url vazio? {not webhook_url}")
    print(f"[CHECKOUT-DEBUG] webhook_url length: {len(webhook_url)}")

    if not handle:
        raise HTTPException(status_code=400, detail="Configure o Handle / Conta antes de gerar o checkout.")
    if not api_base_url:
        raise HTTPException(status_code=400, detail="Configure a URL Base da API antes de gerar o checkout.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="O plano selecionado nao possui valor configurado.")

    plan_key = _resolve_plan_key(user)
    amount_cents = int(round(amount * 100))
    order_nsu = order_nsu or get_renewal_order_nsu(user) or f"PLAN-{user.id}-{plan_key}"
    request_body = {
        "handle": handle,
        "order_nsu": order_nsu,
        "metadata": {
            "user_id": user.id,
            "user_email": user.email,
            "selected_plan": getattr(user, "selected_plan", None),
            "selected_plan_label": user.selected_plan_label,
            "selected_plan_price": amount,
            "order_nsu": order_nsu,
        },
        "external_reference": order_nsu,
        "reference": order_nsu,
        "customer_email": user.email,
        "customer_id": user.id,
        "user_id": user.id,
        "items": [
            {
                "description": user.selected_plan_label or f"Plano {plan_key}",
                "quantity": 1,
                "price": amount_cents,
            }
        ],
        "customer": {
            "name": user.name,
            "email": user.email,
            "id": user.id,
        },
    }

    if webhook_url:
        request_body["webhook_url"] = webhook_url
    if redirect_url:
        request_body["redirect_url"] = redirect_url

    endpoint = links_endpoint if links_endpoint.startswith("/") else f"/{links_endpoint}"
    url = f"{api_base_url}{endpoint}"
    
    # LOG DETALHADO DO PAYLOAD ENVIADO
    print("\n" + "="*80)
    print("[CHECKOUT] ENVIANDO PAYLOAD PARA O GATEWAY")
    print("="*80)
    print(f"[CHECKOUT] URL: {url}")
    print(f"[CHECKOUT] PAYLOAD ENVIADO:")
    print(json.dumps(request_body, indent=2, default=str))
    print("[CHECKOUT] webhook_url incluido?", "webhook_url" in request_body and bool(request_body.get("webhook_url")))
    if webhook_url:
        print(f"[CHECKOUT] webhook_url valor: {webhook_url}")
    print("="*80 + "\n")
    
    return url, request_body, amount_cents, order_nsu


def _extract_payment_status(payload):
    if isinstance(payload, dict):
        candidates = [
            payload.get("status"),
            payload.get("payment_status"),
            payload.get("state"),
            payload.get("paymentState"),
        ]
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.extend([
                data.get("status"),
                data.get("payment_status"),
                data.get("state"),
            ])
        for candidate in candidates:
            if candidate:
                return str(candidate).strip().lower()
    return ""


def _extract_payment_markers(payload):
    positive_markers = ("approved", "paid", "confirm", "success", "completed", "settled", "authorized", "captured", "settled")
    negative_markers = ("pending", "pendente", "waiting", "open", "unpaid", "canceled", "cancelled", "rejected", "failed", "expired")

    def _walk(value):
        status_parts = []
        positive = False
        negative = False

        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).strip().lower()
                if any(marker in key_text for marker in positive_markers):
                    if item in (True, "true", "TRUE", 1, "1", "yes", "YES"):
                        positive = True
                if any(marker in key_text for marker in negative_markers):
                    if item in (True, "true", "TRUE", 1, "1", "yes", "YES"):
                        negative = True
                child_status, child_positive, child_negative = _walk(item)
                if child_status:
                    status_parts.append(child_status)
                positive = positive or child_positive
                negative = negative or child_negative
            for key_name in ("status", "payment_status", "state", "paymentState", "payment_state"):
                if key_name in value and value.get(key_name) is not None:
                    status_parts.append(str(value.get(key_name)).strip().lower())
        elif isinstance(value, list):
            for item in value:
                child_status, child_positive, child_negative = _walk(item)
                if child_status:
                    status_parts.append(child_status)
                positive = positive or child_positive
                negative = negative or child_negative
        elif isinstance(value, bool):
            if value:
                positive = True
        elif value is not None:
            text = str(value).strip().lower()
            if text:
                status_parts.append(text)
                if any(marker in text for marker in positive_markers):
                    positive = True
                if any(marker in text for marker in negative_markers):
                    negative = True

        return " ".join(status_parts), positive, negative

    status_value, has_positive, has_negative = _walk(payload if isinstance(payload, dict) else {})
    message = str(
        (payload or {}).get("message") if isinstance(payload, dict) else ""
    ).strip().lower()
    if message:
        if any(marker in message for marker in positive_markers):
            has_positive = True
        if any(marker in message for marker in negative_markers):
            has_negative = True
        if not status_value:
            status_value = message
    return status_value, has_positive, has_negative


def sync_user_payment_from_gateway(user, db: Session):
    settings = _normalize_payment_settings(getattr(user, "payment_api_settings", None))
    api_base_url = (settings.get("api_base_url") or "").strip().rstrip("/")
    payment_check_endpoint = (settings.get("payment_check_endpoint") or "/payment_check").strip()
    handle = (settings.get("handle") or "").strip()
    order_nsu = get_renewal_order_nsu(user)
    invoice_slug = getattr(user, "renewal_invoice_slug", None)
    if not order_nsu and not invoice_slug:
        return False

    if not api_base_url or not payment_check_endpoint:
        return False

    endpoint = payment_check_endpoint if payment_check_endpoint.startswith("/") else f"/{payment_check_endpoint}"
    url = f"{api_base_url}{endpoint}"
    request_body = {
        "handle": handle,
        "order_nsu": order_nsu,
        "invoice_slug": invoice_slug,
        "customer_email": user.email,
        "external_reference": order_nsu,
        "reference": order_nsu,
    }
    
    print("\n" + "="*80)
    print("[PAYMENT-CHECK] VERIFICANDO STATUS DE PAGAMENTO")
    print("="*80)
    print(f"[PAYMENT-CHECK] URL: {url}")
    print(f"[PAYMENT-CHECK] order_nsu: {order_nsu}")
    print(f"[PAYMENT-CHECK] invoice_slug: {invoice_slug}")
    print("="*80)

    response = None
    data = {}
    for _attempt in range(3):
        for method in ("POST", "GET"):
            try:
                if method == "POST":
                    print(f"\n[PAYMENT-CHECK] Tentativa {_attempt + 1}/3 - Metodo POST")
                    print(f"[PAYMENT-CHECK] PAYLOAD:")
                    print(json.dumps(request_body, indent=2, default=str))
                    response = httpx.post(
                        url,
                        json=request_body,
                        headers={"Content-Type": "application/json"},
                        timeout=15.0,
                    )
                else:
                    print(f"\n[PAYMENT-CHECK] Tentativa {_attempt + 1}/3 - Metodo GET")
                    print(f"[PAYMENT-CHECK] PARAMS:")
                    print(json.dumps(request_body, indent=2, default=str))
                    response = httpx.get(url, params=request_body, timeout=15.0)
                
                # LOG DA RESPOSTA
                print(f"[PAYMENT-CHECK] STATUS: {response.status_code}")
                print(f"[PAYMENT-CHECK] RESPONSE TEXT:")
                print(response.text)
                try:
                    resp_json = response.json()
                    print(f"[PAYMENT-CHECK] RESPONSE JSON:")
                    print(json.dumps(resp_json, indent=2, default=str))
                except:
                    pass
                    
            except httpx.HTTPError as e:
                print(f"[PAYMENT-CHECK] ERRO na tentativa {_attempt + 1}/3: {str(e)}")
                continue

            if response.status_code >= 400:
                print(f"[PAYMENT-CHECK] Status code >= 400, pulando...")
                continue

            try:
                data = response.json()
            except ValueError:
                data = {"raw_response": response.text}

            status_value, is_positive, has_negative = _extract_payment_markers(data)
            print(f"[PAYMENT-CHECK] Status extraido: {status_value}")
            print(f"[PAYMENT-CHECK] Positivo (pago): {is_positive}")
            print(f"[PAYMENT-CHECK] Negativo (nao pago): {has_negative}")
            
            if has_negative:
                print(f"[PAYMENT-CHECK] Pagamento recusado/negado")
                continue
            if is_positive:
                print(f"[PAYMENT-CHECK] PAGAMENTO CONFIRMADO!")
                break
            if response.status_code == 200 and not status_value:
                print(f"[PAYMENT-CHECK] Status 200 OK")
                break
        else:
            continue
        break
    else:
        print("[PAYMENT-CHECK] Todas as tentativas falharam")
        print("="*80 + "\n")
        return False

    print("[PAYMENT-CHECK] Processando resultado...")
    
    _, is_positive, has_negative = _extract_payment_markers(data)
    if has_negative:
        print("[PAYMENT-CHECK] Pagamento negado/recusado")
        print("="*80 + "\n")
        return False
    if not is_positive:
        print("[PAYMENT-CHECK] Pagamento nao confirmado")
        print("="*80 + "\n")
        return False

    print("[PAYMENT-CHECK] RENOVANDO USUARIO...")
    trial_days = get_plan_duration_days(user)
    now = datetime.utcnow()
    base_start = user.trial_expires_at if user.trial_expires_at and user.trial_expires_at > now else now
    user.trial_started_at = now
    user.trial_expires_at = base_start + timedelta(days=trial_days)
    user.is_active = True
    user.block_reason = None
    user.trial_expires_manually_set = False
    user.renewal_order_nsu = None
    user.renewal_order_created_at = None
    db.commit()
    db.refresh(user)
    print("[PAYMENT-CHECK] USUARIO RENOVADO COM SUCESSO!")
    print(f"[PAYMENT-CHECK] Nova expiracao: {user.trial_expires_at}")
    print("="*80 + "\n")
    return True


def create_checkout_link_for_user(user, db: Optional[Session] = None):
    print("\n" + "="*80)
    print(f"[CREATE-CHECKOUT] Gerando checkout para usuario: {user.id} ({user.email})")
    print("="*80)
    
    order_nsu = ensure_renewal_order_nsu(user, db=db)
    print(f"[CREATE-CHECKOUT] order_nsu gerado: {order_nsu}")
    
    url, request_body, _, _ = build_checkout_payload(user, order_nsu=order_nsu)

    try:
        print(f"\n[CREATE-CHECKOUT] Enviando POST ao gateway...")
        response = httpx.post(
            url,
            json=request_body,
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
        print(f"[CREATE-CHECKOUT] Status da resposta: {response.status_code}")
    except httpx.HTTPError as exc:
        print(f"[CREATE-CHECKOUT] ERRO ao conectar ao gateway: {str(exc)}")
        print("="*80 + "\n")
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o gateway: {exc}")

    if response.status_code >= 400:
        print(f"[CREATE-CHECKOUT] ERRO: Gateway retornou {response.status_code}")
        print(f"[CREATE-CHECKOUT] Resposta: {response.text[:500]}")
        print("="*80 + "\n")
        raise HTTPException(
            status_code=502,
            detail=f"Gateway retornou erro ao gerar checkout: {response.text}"
        )

    try:
        gateway_data = response.json()
    except ValueError:
        gateway_data = {"raw_response": response.text}

    checkout_url = gateway_data.get("checkout_url")
    if not checkout_url and isinstance(gateway_data.get("data"), dict):
        checkout_url = (
            gateway_data["data"].get("checkout_url")
            or gateway_data["data"].get("checkout_link")
            or gateway_data["data"].get("url")
        )
    if not checkout_url:
        checkout_url = (
            gateway_data.get("url")
            or gateway_data.get("payment_url")
            or gateway_data.get("checkout_link")
            or gateway_data.get("link")
        )

    if not checkout_url:
        print(f"[CREATE-CHECKOUT] ERRO: Nenhuma URL de checkout na resposta")
        print(f"[CREATE-CHECKOUT] Response: {json.dumps(gateway_data, indent=2, default=str)[:500]}")
        print("="*80 + "\n")
        raise HTTPException(status_code=502, detail="O gateway nao retornou uma URL de checkout valida.")

    checkout_slug = _deep_find_first_string(
        gateway_data,
        {"invoice_slug", "invoiceSlug", "checkout_slug", "checkoutSlug", "slug", "payment_slug", "paymentSlug"}
    )
    if db and checkout_slug:
        user.renewal_invoice_slug = checkout_slug
        db.commit()
        db.refresh(user)

    print(f"[CREATE-CHECKOUT] SUCCESS! URL: {checkout_url[:80]}...")
    print(f"[CREATE-CHECKOUT] order_nsu: {order_nsu}")
    print(f"[CREATE-CHECKOUT] invoice_slug: {checkout_slug}")
    print("="*80 + "\n")

    return checkout_url, gateway_data


def verify_password(plain_password, hashed_password):
    """Verifica se a senha em texto plano corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """Gera o hash da senha."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um token JWT de acesso."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt