from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx


MERCADOPAGO_PREFERENCES_URL = "https://api.mercadopago.com/checkout/preferences"


def build_mercadopago_headers(settings: Dict[str, Any]) -> Dict[str, str]:
    access_token = str(settings.get("mercadopago_access_token") or "").strip()
    if not access_token:
        raise ValueError("Preencha o Access Token do Mercado Pago.")

    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Idempotency-Key": uuid4().hex,
    }


def build_mercadopago_external_reference(user_id: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"MERCADOPAGO-{user_id}-{stamp}"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in str(full_name or "").strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def build_mercadopago_preference_payload(
    *,
    user: Any,
    settings: Dict[str, Any],
    product_name: str,
    amount: float,
    external_reference: Optional[str] = None,
) -> Dict[str, Any]:
    if amount <= 0:
        raise ValueError("O valor do checkout deve ser maior que zero.")

    title = str(product_name or "").strip()
    if not title:
        raise ValueError("Informe o nome do produto.")

    first_name, last_name = _split_name(getattr(user, "name", ""))
    reference = str(external_reference or build_mercadopago_external_reference(getattr(user, "id", 0))).strip()
    if not reference:
        raise ValueError("Não foi possível gerar a referência externa do Mercado Pago.")

    success_url = str(settings.get("mercadopago_success_url") or "").strip()
    pending_url = str(settings.get("mercadopago_pending_url") or "").strip()
    failure_url = str(settings.get("mercadopago_failure_url") or "").strip()
    webhook_url = str(settings.get("mercadopago_webhook_url") or "").strip()
    statement_descriptor = str(settings.get("mercadopago_statement_descriptor") or "").strip()

    payload: Dict[str, Any] = {
        "binary_mode": False,
        "external_reference": reference,
        "statement_descriptor": statement_descriptor or None,
        "items": [
            {
                "id": reference,
                "title": title,
                "description": title,
                "quantity": 1,
                "unit_price": round(float(amount), 2),
                "currency_id": "BRL",
                "category_id": "services",
            }
        ],
        "payer": {
            "email": str(getattr(user, "email", "") or "").strip(),
            "name": first_name,
            "surname": last_name,
        },
        "metadata": {
            "user_id": getattr(user, "id", None),
            "user_email": getattr(user, "email", None),
            "gateway": "mercadopago",
            "external_reference": reference,
        },
        "expires": True,
        "expiration_date_to": (datetime.utcnow() + timedelta(hours=24)).replace(microsecond=0).isoformat() + "Z",
    }

    back_urls = {}
    if success_url:
        back_urls["success"] = success_url
        payload["auto_return"] = "approved"
        if pending_url:
            back_urls["pending"] = pending_url
        if failure_url:
            back_urls["failure"] = failure_url
        payload["back_urls"] = back_urls

    if webhook_url:
        payload["notification_url"] = webhook_url

    if not payload["payer"]["email"]:
        raise ValueError("O usuário precisa ter um e-mail válido para gerar a preference.")

    if not payload["payer"]["name"]:
        payload["payer"].pop("name", None)
    if not payload["payer"]["surname"]:
        payload["payer"].pop("surname", None)
    if not payload.get("statement_descriptor"):
        payload.pop("statement_descriptor", None)

    return payload


async def create_mercadopago_preference(settings: Dict[str, Any], payload: Dict[str, Any]) -> tuple[int, Dict[str, Any], str]:
    headers = build_mercadopago_headers(settings)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(MERCADOPAGO_PREFERENCES_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha ao comunicar com o Mercado Pago: {exc}") from exc

    raw_body = response.text
    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": raw_body}

    return response.status_code, response_data, raw_body


def extract_mercadopago_preference_summary(response_data: Dict[str, Any], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = settings or {}
    checkout_mode = str(settings.get("mercadopago_checkout_mode") or "production").strip().lower()
    init_point = response_data.get("init_point")
    sandbox_init_point = response_data.get("sandbox_init_point")
    preferred_link = sandbox_init_point if checkout_mode == "sandbox" and sandbox_init_point else init_point

    return {
        "gateway_order_id": response_data.get("id"),
        "reference_id": response_data.get("external_reference"),
        "status": response_data.get("status") or "created",
        "payment_link": preferred_link,
        "init_point": init_point,
        "sandbox_init_point": sandbox_init_point,
        "raw": response_data,
    }
