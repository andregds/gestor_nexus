from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import httpx


PAGBANK_ORDERS_ENDPOINT = "/orders"
PAGBANK_API_BASE_URLS = {
    "sandbox": "https://sandbox.api.pagseguro.com",
    "production": "https://api.pagseguro.com",
}


def clean_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_pagbank_orders_url(settings: Dict[str, Any]) -> str:
    environment = str(settings.get("pagbank_environment") or "production").strip().lower()
    base_url = PAGBANK_API_BASE_URLS.get(environment)
    if not base_url:
        raise ValueError("Selecione um ambiente válido do PagBank.")
    return f"{base_url}{PAGBANK_ORDERS_ENDPOINT}"


def build_pagbank_headers(settings: Dict[str, Any]) -> Dict[str, str]:
    access_token = str(settings.get("pagbank_access_token") or "").strip()
    if not access_token:
        raise ValueError("Preencha o Access Token do PagBank.")
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def build_pagbank_reference_id(user_id: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PAGBANK-PF-{user_id}-{stamp}"


def build_pagbank_notification_urls(settings: Dict[str, Any], notification_urls: Optional[Iterable[str]]) -> List[str]:
    normalized = [str(url).strip() for url in (notification_urls or []) if str(url or "").strip()]
    if normalized:
        return normalized

    webhook_url = str(settings.get("pagbank_webhook_url") or "").strip()
    return [webhook_url] if webhook_url else []


def build_pagbank_phone(phone: Dict[str, Any]) -> Dict[str, str]:
    country = clean_digits(phone.get("country") or "55") or "55"
    area = clean_digits(phone.get("area"))
    number = clean_digits(phone.get("number"))
    phone_type = str(phone.get("type") or "MOBILE").strip().upper()

    if len(area) != 2:
        raise ValueError("O DDD do cliente deve ter 2 dígitos.")
    if len(number) not in {8, 9}:
        raise ValueError("O telefone do cliente deve ter 8 ou 9 dígitos.")

    return {
        "country": country,
        "area": area,
        "number": number,
        "type": phone_type,
    }


def build_pagbank_pf_payload(
    *,
    user_id: int,
    settings: Dict[str, Any],
    reference_id: Optional[str],
    customer: Dict[str, Any],
    items: list[Dict[str, Any]],
    notification_urls: Optional[Iterable[str]] = None,
    qr_code_expiration_minutes: int = 30,
) -> Dict[str, Any]:
    resolved_reference_id = str(reference_id or build_pagbank_reference_id(user_id)).strip()
    if not resolved_reference_id:
        raise ValueError("Não foi possível gerar o reference_id do pedido.")

    tax_id = clean_digits(customer.get("tax_id"))
    if len(tax_id) != 11:
        raise ValueError("Para Pessoa Física, informe um CPF válido com 11 dígitos.")

    normalized_items: List[Dict[str, Any]] = []
    total_amount = 0
    for item in items:
        quantity = int(item.get("quantity") or 0)
        unit_amount = int(item.get("unit_amount") or 0)
        if quantity <= 0:
            raise ValueError("Cada item deve ter quantidade maior que zero.")
        if unit_amount <= 0:
            raise ValueError("Cada item deve ter unit_amount maior que zero em centavos.")

        normalized_item = {
            "reference_id": str(item.get("reference_id") or item.get("sku") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "quantity": quantity,
            "unit_amount": unit_amount,
        }
        if not normalized_item["reference_id"]:
            raise ValueError("Cada item precisa de um SKU ou reference_id.")
        if not normalized_item["name"]:
            raise ValueError("Cada item precisa de um nome.")

        normalized_items.append(normalized_item)
        total_amount += quantity * unit_amount

    if total_amount <= 0:
        raise ValueError("O pedido precisa ter valor total maior que zero.")

    phones = customer.get("phones") or []
    if not phones:
        raise ValueError("Informe pelo menos um telefone do comprador.")

    expiration = datetime.utcnow() + timedelta(minutes=max(1, int(qr_code_expiration_minutes or 30)))
    payload = {
        "reference_id": resolved_reference_id,
        "customer": {
            "name": str(customer.get("name") or "").strip(),
            "email": str(customer.get("email") or "").strip(),
            "tax_id": tax_id,
            "phones": [build_pagbank_phone(phone) for phone in phones],
        },
        "items": normalized_items,
        "qr_codes": [
            {
                "amount": {"value": total_amount},
                "expiration_date": expiration.replace(microsecond=0).isoformat() + "Z",
            }
        ],
        "notification_urls": build_pagbank_notification_urls(settings, notification_urls),
    }

    if not payload["customer"]["name"]:
        raise ValueError("Informe o nome do comprador.")
    if not payload["customer"]["email"]:
        raise ValueError("Informe o e-mail do comprador.")

    return payload


async def create_pagbank_order(settings: Dict[str, Any], payload: Dict[str, Any]) -> tuple[int, Dict[str, Any], str]:
    url = build_pagbank_orders_url(settings)
    headers = build_pagbank_headers(settings)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha ao comunicar com o PagBank: {exc}") from exc

    raw_body = response.text
    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": raw_body}

    return response.status_code, response_data, raw_body


def _extract_link(payload: Any, rel_candidates: set[str]) -> Optional[str]:
    if isinstance(payload, dict):
        links = payload.get("links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                rel = str(link.get("rel") or "").strip().upper()
                href = str(link.get("href") or "").strip()
                if rel in rel_candidates and href:
                    return href
        for value in payload.values():
            result = _extract_link(value, rel_candidates)
            if result:
                return result
    elif isinstance(payload, list):
        for item in payload:
            result = _extract_link(item, rel_candidates)
            if result:
                return result
    return None


def extract_pagbank_order_summary(response_data: Dict[str, Any]) -> Dict[str, Any]:
    qr_codes = response_data.get("qr_codes") if isinstance(response_data.get("qr_codes"), list) else []
    first_qr_code = qr_codes[0] if qr_codes and isinstance(qr_codes[0], dict) else {}
    amount = first_qr_code.get("amount") if isinstance(first_qr_code.get("amount"), dict) else {}

    return {
        "gateway_order_id": response_data.get("id"),
        "reference_id": response_data.get("reference_id"),
        "status": response_data.get("status"),
        "payment_link": _extract_link(response_data, {"PAY"}),
        "qr_code_text": first_qr_code.get("text") or first_qr_code.get("payload") or first_qr_code.get("emv"),
        "qr_code_png": _extract_link(first_qr_code, {"QRCODE.PNG", "QRCODE", "IMAGE"}),
        "qr_code_amount": amount.get("value"),
        "raw": response_data,
    }
