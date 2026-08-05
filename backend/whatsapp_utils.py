# backend/whatsapp_utils.py
import base64
import binascii
import json
import logging
import re

import httpx
from fastapi import HTTPException

from core.config import get_waha_api_key, get_waha_api_url

logger = logging.getLogger("uvicorn")


def waha_headers(include_json_content_type=True):
    api_key = get_waha_api_key()
    headers = {"X-Api-Key": api_key} if api_key else {}
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    return headers


def _mask_value(value: str, keep: int = 4) -> str:
    text = str(value or "")
    if len(text) <= keep:
        return "*" * len(text)
    return ("*" * max(len(text) - keep, 0)) + text[-keep:]


def _truncate_text(value, limit: int = 800) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncado {len(text) - limit} chars]"


def _log_api_request(method: str, url: str, *, headers=None, json_body=None):
    safe_headers = dict(headers or {})
    if safe_headers.get("X-Api-Key"):
        safe_headers["X-Api-Key"] = _mask_value(safe_headers["X-Api-Key"])

    payload_parts = [f"[WHATSAPP][REQUEST] {method} {url}"]
    if safe_headers:
        payload_parts.append(f"headers={_truncate_text(safe_headers)}")
    if json_body is not None:
        payload_parts.append(f"json={_truncate_text(json_body)}")

    logger.info(" | ".join(payload_parts))


def _log_api_response(action: str, response: httpx.Response):
    logger.info(
        "[WHATSAPP][RESPONSE] %s | status=%s | body=%s",
        action,
        response.status_code,
        _truncate_text(response.text or ""),
    )


def _log_whatsapp_event(event: str, **context):
    if context:
        logger.info("[WHATSAPP] %s | %s", event, _truncate_text(context))
        return
    logger.info("[WHATSAPP] %s", event)


def _build_waha_send_result(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    message_id = None
    if isinstance(data, dict):
        message_id = data.get("id") or data.get("messageId")
        if not message_id and isinstance(data.get("_data"), dict):
            message_id = data["_data"].get("id")

    return {
        "accepted": response.status_code in [200, 201],
        "delivered": False,
        "gateway_status": "ACCEPTED" if response.status_code in [200, 201] else "ERROR",
        "gateway_response": data,
        "message_id": message_id,
    }


def _waha_session_status(data) -> str:
    if isinstance(data, dict):
        return str(data.get("status") or "").strip().upper()
    return "UNKNOWN"


def _waha_status_to_state(status: str) -> str:
    normalized = str(status or "").upper()
    if normalized == "WORKING":
        return "open"
    if normalized in {"SCAN_QR_CODE", "STARTING", "STOPPED", "FAILED"}:
        return normalized
    return normalized or "UNKNOWN"


async def create_whatsapp_session(session_name: str) -> bool:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        return False

    payload = {"name": session_name, "start": True}
    url = f"{waha_api_url}/api/sessions/"

    async with httpx.AsyncClient() as client:
        try:
            _log_api_request("POST", url, headers=waha_headers(), json_body=payload)
            response = await client.post(url, headers=waha_headers(), json=payload, timeout=15.0)
            _log_api_response("waha_create_session", response)

            if response.status_code in [200, 201]:
                return True
            if response.status_code in [409, 422] and "already exists" in (response.text or "").lower():
                return await start_whatsapp_session(session_name)

            logger.error("Falha ao criar sessão WAHA: %s", response.text)
        except Exception as exc:
            logger.error("Erro de conexão com WAHA ao criar sessão: %s", exc)
    return False


async def start_whatsapp_session(session_name: str) -> bool:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        return False

    url = f"{waha_api_url}/api/sessions/{session_name}/start"
    async with httpx.AsyncClient() as client:
        try:
            _log_api_request("POST", url, headers=waha_headers())
            response = await client.post(url, headers=waha_headers(), timeout=15.0)
            _log_api_response("waha_start_session", response)
            return response.status_code in [200, 201]
        except Exception as exc:
            logger.error("Erro de conexão com WAHA ao iniciar sessão: %s", exc)
            return False


async def get_instance_state_and_qr(session_name: str) -> dict:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        return {}

    async with httpx.AsyncClient() as client:
        try:
            url_state = f"{waha_api_url}/api/sessions/{session_name}"
            _log_api_request("GET", url_state, headers=waha_headers())
            response_state = await client.get(url_state, headers=waha_headers(), timeout=10.0)
            _log_api_response("waha_session_state", response_state)

            if response_state.status_code == 404:
                created = await create_whatsapp_session(session_name)
                if not created:
                    return {"state": "ERROR", "message": "Sessão WAHA não encontrada e não pôde ser criada."}
                response_state = await client.get(url_state, headers=waha_headers(), timeout=10.0)

            state = "UNKNOWN"
            qr_code = None
            if response_state.status_code == 200:
                state_data = response_state.json()
                state = _waha_status_to_state(_waha_session_status(state_data))

            if state != "open":
                url_qr = f"{waha_api_url}/api/{session_name}/auth/qr"
                _log_api_request("GET", url_qr, headers=waha_headers())
                response_qr = await client.get(url_qr, headers=waha_headers(), timeout=15.0)
                _log_api_response("waha_auth_qr", response_qr)

                if response_qr.status_code in [200, 201]:
                    content_type = response_qr.headers.get("content-type", "")
                    if "image/" in content_type:
                        qr_code = f"data:{content_type.split(';', 1)[0]};base64,{base64.b64encode(response_qr.content).decode('ascii')}"
                    else:
                        try:
                            qr_data = response_qr.json()
                        except ValueError:
                            qr_data = {}
                        qr_code = (
                            qr_data.get("qr")
                            or qr_data.get("qrcode")
                            or qr_data.get("base64")
                            or qr_data.get("data")
                        )

            return {"state": state, "qr_code": qr_code, "message": "Sucesso"}
        except Exception as exc:
            logger.error("Erro status WAHA: %s", exc)
            return {"state": "ERROR", "message": str(exc)}


async def delete_whatsapp_session(session_name: str) -> bool:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        return False

    url = f"{waha_api_url}/api/sessions/{session_name}/"
    async with httpx.AsyncClient() as client:
        try:
            _log_api_request("DELETE", url, headers=waha_headers())
            response = await client.delete(url, headers=waha_headers(), timeout=10.0)
            _log_api_response("waha_delete_session", response)
            return response.status_code in [200, 204, 404]
        except Exception as exc:
            logger.error("Erro ao remover sessão WAHA: %s", exc)
            return False


async def configure_waha_webhook(session_name: str, webhook_url: str) -> dict:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        raise RuntimeError("WAHA API não configurada.")
    if not session_name:
        raise RuntimeError("Sessão WAHA não informada.")
    if not webhook_url:
        raise RuntimeError("URL pública de webhook não informada.")

    payload = {
        "name": session_name,
        "config": {
            "webhooks": [
                {
                    "url": webhook_url,
                    "events": ["session.status", "message", "message.ack"],
                }
            ]
        },
    }
    url = f"{waha_api_url}/api/sessions/{session_name}/"

    async with httpx.AsyncClient() as client:
        _log_api_request("POST", url, headers=waha_headers(), json_body=payload)
        response = await client.post(url, headers=waha_headers(), json=payload, timeout=15.0)
        _log_api_response("waha_configure_webhook", response)

    if response.status_code not in [200, 201]:
        raise RuntimeError(f"WAHA API retornou {response.status_code} ao configurar webhook: {response.text}")

    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


def _parse_media_data_url(data_url: str):
    if not isinstance(data_url, str) or not data_url.startswith("data:") or ";base64," not in data_url:
        raise HTTPException(status_code=400, detail="Imagem de lembrete inválida. Reenvie o arquivo.")

    header, encoded = data_url.split(",", 1)
    header_body = header[5:]
    mime_type, separator, _ = header_body.partition(";base64")
    if not separator or not mime_type:
        raise HTTPException(status_code=400, detail="Imagem de lembrete inválida. Reenvie o arquivo.")

    try:
        payload = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Imagem de lembrete inválida. Reenvie o arquivo.")

    return mime_type, payload


def _response_text(response: httpx.Response) -> str:
    try:
        return str(response.json()).lower()
    except Exception:
        return (response.text or "").lower()


def _is_whatsapp_number_not_found_error(response: httpx.Response) -> bool:
    text = _response_text(response)
    if not text:
        return False

    exact_markers = [
        "nao possui conta no whatsapp",
        "não possui conta no whatsapp",
        "does not have whatsapp",
        "not registered on whatsapp",
        "number not found",
        "recipient not found",
        "unregistered whatsapp",
        "invalid whatsapp number",
        "no whatsapp account",
    ]
    if any(marker in text for marker in exact_markers):
        return True

    return '"exists":false' in text or '"exists": false' in text or "'exists': false" in text


def _is_whatsapp_session_missing_error(response: httpx.Response) -> bool:
    text = _response_text(response)
    if not text:
        return False

    markers = [
        "sessionerror: no sessions",
        "no sessions",
        "session not found",
        "instance not connected",
    ]
    return any(marker in text for marker in markers)


async def _resolve_waha_chat_id(clean_number: str, session_name: str) -> str:
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        return f"{clean_number}@c.us"

    url = f"{waha_api_url}/api/contacts/check-exists"
    params = {"phone": clean_number, "session": session_name}

    async with httpx.AsyncClient() as client:
        try:
            _log_api_request("GET", url, headers=waha_headers(), json_body=params)
            response = await client.get(url, headers=waha_headers(), params=params, timeout=10.0)
            _log_api_response("waha_check_number", response)
            if response.status_code == 200:
                data = response.json()
                if data.get("numberExists") is False:
                    raise HTTPException(status_code=400, detail=f"O número {clean_number} não possui conta no WhatsApp.")
                chat_id = data.get("chatId")
                if chat_id:
                    return chat_id
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Falha ao validar número na WAHA; usando chatId padrão. erro=%s", exc)

    return f"{clean_number}@c.us"


async def _send_waha_text(number: str, message: str, session_name: str):
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        raise HTTPException(status_code=503, detail="WAHA API não configurada. Defina WAHA_API_URL e WAHA_API_KEY.")
    if not session_name:
        raise HTTPException(status_code=400, detail="Sessão WhatsApp não configurada.")

    clean_number = re.sub(r"\D", "", str(number))
    chat_id = await _resolve_waha_chat_id(clean_number, session_name)
    payload = {
        "session": session_name,
        "chatId": chat_id,
        "text": message,
    }
    url = f"{waha_api_url}/api/sendText"

    async with httpx.AsyncClient() as client:
        try:
            _log_whatsapp_event(
                "Preparando envio de texto WAHA",
                session_name=session_name,
                number=clean_number,
                chat_id=chat_id,
                message=message,
            )
            _log_api_request("POST", url, headers=waha_headers(), json_body=payload)
            response = await client.post(url, headers=waha_headers(), json=payload, timeout=15.0)
            _log_api_response("waha_send_text", response)

            if response.status_code in [200, 201]:
                result = _build_waha_send_result(response)
                _log_whatsapp_event("Resultado envio de texto WAHA", **result)
                return result

            if response.status_code in [400, 404]:
                if _is_whatsapp_session_missing_error(response):
                    raise HTTPException(
                        status_code=409,
                        detail="WhatsApp desconectado. Gere um novo QR Code na aba Integração e conecte a sessão novamente.",
                    )
                if _is_whatsapp_number_not_found_error(response):
                    raise HTTPException(status_code=400, detail=f"O número {clean_number} não possui conta no WhatsApp.")

            logger.error("Erro envio WAHA: %s - %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail=f"WAHA API retornou {response.status_code}: {response.text}")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Exceção envio WAHA: %s", exc)
            raise HTTPException(status_code=502, detail=f"Falha ao enviar mensagem via WAHA: {exc}")


async def _send_waha_image(number: str, message: str, session_name: str, media: dict):
    waha_api_url = get_waha_api_url()
    if not waha_api_url:
        raise HTTPException(status_code=503, detail="WAHA API não configurada. Defina WAHA_API_URL e WAHA_API_KEY.")
    if not session_name:
        raise HTTPException(status_code=400, detail="Sessão WhatsApp não configurada.")

    clean_number = re.sub(r"\D", "", str(number))
    chat_id = await _resolve_waha_chat_id(clean_number, session_name)
    mime_type, media_bytes = _parse_media_data_url(media.get("data_url", ""))
    file_name = str(media.get("file_name") or "lembrete").strip() or "lembrete"
    if "." not in file_name:
        extension = mime_type.split("/")[-1] if "/" in mime_type else "png"
        file_name = f"{file_name}.{extension}"

    payload = {
        "session": session_name,
        "chatId": chat_id,
        "file": {
            "mimetype": mime_type,
            "filename": file_name,
            "data": base64.b64encode(media_bytes).decode("ascii"),
        },
        "caption": message or "",
    }
    url = f"{waha_api_url}/api/sendImage"

    async with httpx.AsyncClient() as client:
        try:
            _log_whatsapp_event(
                "Preparando envio de imagem WAHA",
                session_name=session_name,
                number=clean_number,
                chat_id=chat_id,
                file_name=file_name,
                mime_type=mime_type,
            )
            safe_payload = {**payload, "file": {**payload["file"], "data": "[base64]"}}
            _log_api_request("POST", url, headers=waha_headers(), json_body=safe_payload)
            response = await client.post(url, headers=waha_headers(), json=payload, timeout=30.0)
            _log_api_response("waha_send_image", response)

            if response.status_code in [200, 201]:
                result = _build_waha_send_result(response)
                _log_whatsapp_event("Resultado envio de imagem WAHA", **result)
                return result

            if response.status_code in [400, 404]:
                if _is_whatsapp_session_missing_error(response):
                    raise HTTPException(
                        status_code=409,
                        detail="WhatsApp desconectado. Gere um novo QR Code na aba Integração e conecte a sessão novamente.",
                    )
                if _is_whatsapp_number_not_found_error(response):
                    raise HTTPException(status_code=400, detail=f"O número {clean_number} não possui conta no WhatsApp.")

            logger.error("Erro envio imagem WAHA: %s - %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail=f"WAHA API retornou {response.status_code}: {response.text}")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Exceção envio imagem WAHA: %s", exc)
            raise HTTPException(status_code=502, detail=f"Falha ao enviar imagem via WAHA: {exc}")


async def send_whatsapp_notification(number: str, message: str, instance_name: str, media=None):
    if media and isinstance(media, dict) and media.get("data_url"):
        return await _send_waha_image(number, message, instance_name, media)
    return await _send_waha_text(number, message, instance_name)


def generate_instance_name(user):
    import time
    user_id = user.id if hasattr(user, "id") else user
    return f"monitor_user_{user_id}_{int(time.time())}"
