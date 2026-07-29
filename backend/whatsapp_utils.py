# backend/whatsapp_utils.py
import base64
import binascii
import json
import logging
import re

import httpx
from fastapi import HTTPException
from core.config import get_evolution_api_key, get_evolution_api_url

logger = logging.getLogger("uvicorn")


def evolution_headers(include_json_content_type=True):
    api_key = get_evolution_api_key()
    headers = {"apikey": api_key} if api_key else {}
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
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


def _log_evolution_request(method: str, url: str, *, headers=None, json_body=None, form_data=None, files=None):
    safe_headers = dict(headers or {})
    if safe_headers.get("apikey"):
        safe_headers["apikey"] = _mask_value(safe_headers["apikey"])

    payload_parts = [f"[WHATSAPP][REQUEST] {method} {url}"]
    if safe_headers:
        payload_parts.append(f"headers={_truncate_text(safe_headers)}")
    if json_body is not None:
        payload_parts.append(f"json={_truncate_text(json_body)}")
    if form_data is not None:
        payload_parts.append(f"form={_truncate_text(form_data)}")
    if files is not None:
        safe_files = {
            key: {
                "file_name": value[0],
                "content_type": value[2],
                "size_bytes": len(value[1]) if len(value) > 1 and isinstance(value[1], (bytes, bytearray)) else None,
            }
            for key, value in files.items()
        }
        payload_parts.append(f"files={_truncate_text(safe_files)}")

    logger.info(" | ".join(payload_parts))


def _log_evolution_response(action: str, response: httpx.Response):
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


def _build_send_result(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    gateway_status = str(data.get("status") or "").strip().upper()
    delivered = gateway_status in {"DELIVERED", "READ"}
    accepted = response.status_code in [200, 201]

    return {
        "accepted": accepted,
        "delivered": delivered,
        "gateway_status": gateway_status or "UNKNOWN",
        "gateway_response": data,
        "message_id": ((data.get("key") or {}).get("id") if isinstance(data.get("key"), dict) else None),
    }


def _default_evolution_webhook_events():
    return [
        "CONNECTION_UPDATE",
        "SEND_MESSAGE",
        "MESSAGES_UPDATE",
    ]


async def evolution_create_instance(instance_name: str):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        return False

    payload = {
        "instanceName": instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS"
    }

    url = f"{evolution_api_url}/instance/create"

    async with httpx.AsyncClient() as client:
        try:
            _log_evolution_request("POST", url, headers=evolution_headers(), json_body=payload)
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)
            _log_evolution_response("create_instance", response)
            if response.status_code in [200, 201]:
                return True
            logger.error(f"Falha ao criar instância: {response.text}")
        except Exception as e:
            logger.error(f"Erro de conexão: {e}")
    return False


async def get_instance_state_and_qr(instance_name: str):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        return {}

    async with httpx.AsyncClient() as client:
        try:
            # 1. Busca Estado
            url_state = f"{evolution_api_url}/instance/connectionState/{instance_name}"
            _log_evolution_request("GET", url_state, headers=evolution_headers())
            response_state = await client.get(url_state, headers=evolution_headers(), timeout=5.0)
            _log_evolution_response("connection_state", response_state)

            state = "unknown"
            qr_code = None

            if response_state.status_code == 200:
                data = response_state.json()
                state = data.get("instance", {}).get("state") or data.get("state", "unknown")
                qr_code = data.get("qrcode", {}).get("base64") or data.get("qrcode")

            # 2. Tenta conectar se necessário
            if state not in ["open", "connected"] and not qr_code:
                url_connect = f"{evolution_api_url}/instance/connect/{instance_name}"
                try:
                    _log_evolution_request("GET", url_connect, headers=evolution_headers())
                    response_connect = await client.get(url_connect, headers=evolution_headers(), timeout=5.0)
                    _log_evolution_response("connect_instance", response_connect)
                    if response_connect.status_code == 200:
                        data_connect = response_connect.json()
                        qr_code = data_connect.get("base64") or data_connect.get("qrcode", {}).get("base64")
                except Exception:
                    pass

            return {"state": state, "qr_code": qr_code, "message": "Sucesso"}
        except Exception as e:
            logger.error(f"Erro status: {e}")
            return {"state": "ERROR", "message": str(e)}


async def evolution_delete_instance(instance_name: str):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        return False
    url = f"{evolution_api_url}/instance/delete/{instance_name}"
    async with httpx.AsyncClient() as client:
        try:
            _log_evolution_request("DELETE", url, headers=evolution_headers())
            response = await client.delete(url, headers=evolution_headers(), timeout=5.0)
            _log_evolution_response("delete_instance", response)
            return True
        except Exception:
            return False


async def configure_evolution_webhook(instance_name: str, webhook_url: str, events=None) -> dict:
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        raise RuntimeError("Evolution API não configurada.")
    if not instance_name:
        raise RuntimeError("Instância WhatsApp não informada.")
    if not webhook_url:
        raise RuntimeError("URL pública de webhook não informada.")

    payload = {
        "enabled": True,
        "url": webhook_url,
        "webhook_by_events": False,
        "base64": False,
        "events": events or _default_evolution_webhook_events(),
    }
    url = f"{evolution_api_url}/webhook/set/{instance_name}"

    async with httpx.AsyncClient() as client:
        try:
            _log_evolution_request("POST", url, headers=evolution_headers(), json_body=payload)
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)
            _log_evolution_response("set_webhook", response)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Falha ao configurar webhook na Evolution API: {exc}") from exc

    if response.status_code not in [200, 201]:
        raise RuntimeError(f"Evolution API retornou {response.status_code} ao configurar webhook: {response.text}")

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

    if '"exists":false' in text or '"exists": false' in text or "'exists': false" in text:
        return True

    return False


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


async def _send_whatsapp_media(number: str, message: str, instance_name: str, media: dict):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        raise HTTPException(
            status_code=503,
            detail="Evolution API não configurada. Defina EVOLUTION_API_URL e EVOLUTION_API_KEY.",
        )
    if not instance_name:
        raise HTTPException(status_code=400, detail="Instância WhatsApp não configurada.")

    clean_number = re.sub(r"\D", "", str(number))
    mime_type, media_bytes = _parse_media_data_url(media.get("data_url", ""))
    file_name = str(media.get("file_name") or "lembrete").strip() or "lembrete"
    if "." not in file_name:
        extension = mime_type.split("/")[-1] if "/" in mime_type else "png"
        file_name = f"{file_name}.{extension}"

    form_data = {
        "number": clean_number,
        "mediatype": "image",
        "caption": message or "",
        "fileName": file_name,
    }
    files = {
        "media": (file_name, media_bytes, mime_type),
    }
    url = f"{evolution_api_url}/message/sendMedia/{instance_name}"

    async with httpx.AsyncClient() as client:
        try:
            _log_whatsapp_event(
                "Preparando envio de mídia",
                instance_name=instance_name,
                number=clean_number,
                file_name=file_name,
                mime_type=mime_type,
            )
            _log_evolution_request(
                "POST",
                url,
                headers=evolution_headers(include_json_content_type=False),
                form_data=form_data,
                files=files,
            )
            response = await client.post(
                url,
                headers=evolution_headers(include_json_content_type=False),
                data=form_data,
                files=files,
                timeout=20.0,
            )
            _log_evolution_response("send_media", response)

            if response.status_code in [200, 201]:
                result = _build_send_result(response)
                _log_whatsapp_event("Resultado envio de mídia", **result)
                return result

            if response.status_code == 400:
                try:
                    if _is_whatsapp_session_missing_error(response):
                        logger.warning("⚠️ Instância WhatsApp sem sessão ativa detectada")
                        raise HTTPException(
                            status_code=409,
                            detail="WhatsApp desconectado. Gere um novo QR Code na aba Integração e conecte a instância novamente.",
                        )
                    if _is_whatsapp_number_not_found_error(response):
                        logger.warning(f"⚠️ Número inválido detectado: {clean_number}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"O número {clean_number} não possui conta no WhatsApp."
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

            logger.error(f"Erro envio de mídia: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Evolution API retornou {response.status_code}: {response.text}",
            )
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Exceção envio de mídia: {e}")
            raise HTTPException(status_code=502, detail=f"Falha ao enviar mídia: {e}")


async def send_whatsapp_notification(number: str, message: str, instance_name: str, media=None):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        raise HTTPException(
            status_code=503,
            detail="Evolution API não configurada. Defina EVOLUTION_API_URL e EVOLUTION_API_KEY.",
        )
    if not instance_name:
        raise HTTPException(status_code=400, detail="Instância WhatsApp não configurada.")

    if media and isinstance(media, dict) and media.get("data_url"):
        return await _send_whatsapp_media(number, message, instance_name, media)

    clean_number = re.sub(r'\D', '', str(number))
    payload = {
        "number": clean_number,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": message}
    }
    url = f"{evolution_api_url}/message/sendText/{instance_name}"

    async with httpx.AsyncClient() as client:
        try:
            _log_whatsapp_event(
                "Preparando envio de texto",
                instance_name=instance_name,
                number=clean_number,
                message=message,
            )
            _log_evolution_request("POST", url, headers=evolution_headers(), json_body=payload)
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)
            _log_evolution_response("send_text", response)

            if response.status_code in [200, 201]:
                result = _build_send_result(response)
                _log_whatsapp_event("Resultado envio de texto", **result)
                return result

            # --- CORREÇÃO AQUI ---
            # Tratamento específico para erro 400 (Número inválido)
            if response.status_code == 400:
                try:
                    if _is_whatsapp_session_missing_error(response):
                        logger.warning("⚠️ Instância WhatsApp sem sessão ativa detectada")
                        raise HTTPException(
                            status_code=409,
                            detail="WhatsApp desconectado. Gere um novo QR Code na aba Integração e conecte a instância novamente.",
                        )
                    if _is_whatsapp_number_not_found_error(response):
                        logger.warning(f"⚠️ Número inválido detectado: {clean_number}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"O número {clean_number} não possui conta no WhatsApp."
                        )
                except HTTPException:
                    raise  # Propaga a exceção para a rota
                except Exception:
                    pass  # Se falhar o parse, continua para o log de erro genérico
            # ---------------------

            logger.error(f"Erro envio: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Evolution API retornou {response.status_code}: {response.text}",
            )

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Exceção envio: {e}")
            raise HTTPException(status_code=502, detail=f"Falha ao enviar mensagem: {e}")


def generate_instance_name(user):
    import time
    user_id = user.id if hasattr(user, 'id') else user
    return f"monitor_user_{user_id}_{int(time.time())}"