# backend/core/security.py
from datetime import datetime, timedelta
from typing import Optional
import httpx
from uuid import uuid4
import bcrypt
from jose import jwt
import os
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

# Configurações de Segurança
# Em produção, certifique-se de ter SECRET_KEY no seu arquivo .env
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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


_SENSITIVE_KEYS = {"api_key", "webhook_secret", "apikey", "secret", "password", "token", "email"}


def _mask_sensitive(value):
    """Retorna uma copia do payload com chaves sensiveis mascaradas para log seguro.

    Evita registrar segredos (api_key, webhook_secret) e reduz exposicao de PII,
    conforme politica de privacidade (nunca logar segredos em texto puro).
    """
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if any(marker in key_text for marker in _SENSITIVE_KEYS) and item:
                masked[key] = "***REDACTED***"
            else:
                masked[key] = _mask_sensitive(item)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


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

    # Log seguro: nunca registrar api_key / webhook_secret em texto puro.
    logger.debug("[CHECKOUT] Settings (mascarado): %s", _mask_sensitive(settings))
    
    handle = (settings.get("handle") or "").strip()
    api_base_url = (settings.get("api_base_url") or "").strip().rstrip("/")
    links_endpoint = (settings.get("links_endpoint") or "/links").strip()
    webhook_url = (settings.get("webhook_url") or "").strip()
    redirect_url = (settings.get("redirect_url") or "").strip()
    amount = get_plan_price(user)
    
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

    # Log seguro: PII (e-mail do cliente) mascarada e sem segredos.
    logger.debug("[CHECKOUT] Enviando payload para %s (payload mascarado: %s)",
                 url, _mask_sensitive(request_body))

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
    
    logger.debug("[PAYMENT-CHECK] Verificando pagamento em %s (order_nsu=%s, invoice_slug=%s)",
                 url, order_nsu, invoice_slug)

    response = None
    data = {}
    for _attempt in range(3):
        for method in ("POST", "GET"):
            try:
                if method == "POST":
                    logger.debug("[PAYMENT-CHECK] Tentativa %s/3 - POST (payload mascarado: %s)",
                                 _attempt + 1, _mask_sensitive(request_body))
                    response = httpx.post(
                        url,
                        json=request_body,
                        headers={"Content-Type": "application/json"},
                        timeout=15.0,
                    )
                else:
                    logger.debug("[PAYMENT-CHECK] Tentativa %s/3 - GET (params mascarados: %s)",
                                 _attempt + 1, _mask_sensitive(request_body))
                    response = httpx.get(url, params=request_body, timeout=15.0)

                logger.debug("[PAYMENT-CHECK] Status HTTP: %s", response.status_code)

            except httpx.HTTPError as e:
                logger.warning("[PAYMENT-CHECK] Erro na tentativa %s/3: %s", _attempt + 1, str(e))
                continue

            if response.status_code >= 400:
                logger.debug("[PAYMENT-CHECK] Status code >= 400, pulando...")
                continue

            try:
                data = response.json()
            except ValueError:
                data = {"raw_response": response.text}

            status_value, is_positive, has_negative = _extract_payment_markers(data)
            logger.debug("[PAYMENT-CHECK] status=%s positivo=%s negativo=%s",
                         status_value, is_positive, has_negative)

            if has_negative:
                continue
            if is_positive:
                break
            if response.status_code == 200 and not status_value:
                break
        else:
            continue
        break
    else:
        logger.info("[PAYMENT-CHECK] Todas as tentativas falharam")
        return False

    _, is_positive, has_negative = _extract_payment_markers(data)
    if has_negative:
        logger.info("[PAYMENT-CHECK] Pagamento negado/recusado")
        return False
    if not is_positive:
        logger.info("[PAYMENT-CHECK] Pagamento nao confirmado")
        return False

    logger.info("[PAYMENT-CHECK] Renovando usuario %s...", user.id)
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
    logger.info("[PAYMENT-CHECK] Usuario %s renovado. Nova expiracao: %s", user.id, user.trial_expires_at)
    return True


def create_checkout_link_for_user(user, db: Optional[Session] = None):
    logger.info("[CREATE-CHECKOUT] Gerando checkout para usuario %s", user.id)

    order_nsu = ensure_renewal_order_nsu(user, db=db)
    logger.debug("[CREATE-CHECKOUT] order_nsu gerado: %s", order_nsu)

    url, request_body, _, _ = build_checkout_payload(user, order_nsu=order_nsu)

    try:
        response = httpx.post(
            url,
            json=request_body,
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
        logger.debug("[CREATE-CHECKOUT] Status da resposta: %s", response.status_code)
    except httpx.HTTPError as exc:
        logger.error("[CREATE-CHECKOUT] Erro ao conectar ao gateway: %s", str(exc))
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o gateway: {exc}")

    if response.status_code >= 400:
        logger.error("[CREATE-CHECKOUT] Gateway retornou %s", response.status_code)
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
        logger.error("[CREATE-CHECKOUT] Nenhuma URL de checkout na resposta do gateway")
        raise HTTPException(status_code=502, detail="O gateway nao retornou uma URL de checkout valida.")

    checkout_slug = _deep_find_first_string(
        gateway_data,
        {"invoice_slug", "invoiceSlug", "checkout_slug", "checkoutSlug", "slug", "payment_slug", "paymentSlug"}
    )
    if db and checkout_slug:
        user.renewal_invoice_slug = checkout_slug
        db.commit()
        db.refresh(user)

    logger.info("[CREATE-CHECKOUT] Checkout gerado (order_nsu=%s, invoice_slug=%s)", order_nsu, checkout_slug)

    return checkout_url, gateway_data


def verify_password(plain_password, hashed_password):
    """Verifica se a senha em texto plano corresponde ao hash."""
    plain_password_bytes = _normalize_password_bytes(plain_password)
    hashed_password_bytes = _normalize_password_bytes(hashed_password, allow_empty=True)
    if not hashed_password_bytes:
        return False
    return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)


def get_password_hash(password):
    """Gera o hash da senha."""
    password_bytes = _normalize_password_bytes(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def _normalize_password_bytes(value, allow_empty=False):
    if value is None:
        return b"" if allow_empty else b""
    if isinstance(value, bytes):
        normalized = value
    elif isinstance(value, bytearray):
        normalized = bytes(value)
    elif isinstance(value, str):
        normalized = value.encode("utf-8")
    else:
        normalized = str(value).encode("utf-8")
    return normalized[:72]


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