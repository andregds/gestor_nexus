# backend/whatsapp_utils.py
import base64
import binascii
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
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)
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
            response_state = await client.get(url_state, headers=evolution_headers(), timeout=5.0)

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
                    response_connect = await client.get(url_connect, headers=evolution_headers(), timeout=5.0)
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
            await client.delete(url, headers=evolution_headers(), timeout=5.0)
            return True
        except Exception:
            return False


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


async def _send_whatsapp_media(number: str, message: str, instance_name: str, media: dict):
    evolution_api_url = get_evolution_api_url()
    if not evolution_api_url:
        raise HTTPException(status_code=503, detail="Evolution API não configurada.")
    if not instance_name:
        raise HTTPException(status_code=400, detail="Instância WhatsApp não configurada.")

    clean_number = re.sub(r"\D", "", str(number))
    mime_type, media_bytes = _parse_media_data_url(media.get("data_url", ""))
    file_name = str(media.get("file_name") or "lembrete").strip() or "lembrete"
    if "." not in file_name:
        extension = mime_type.split("/")[-1] if "/" in mime_type else "png"
        file_name = f"{file_name}.{extension}"

    media_payload = {
        "mediatype": "image",
        "caption": message or "",
        "fileName": file_name,
        "media": base64.b64encode(media_bytes).decode("ascii"),
        "mimetype": mime_type,
        "number": clean_number,
    }
    payload = {
        "number": clean_number,
        "mediaMessage": media_payload,
    }
    url = f"{evolution_api_url}/message/sendMedia/{instance_name}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers=evolution_headers(),
                json=payload,
                timeout=20.0,
            )

            if response.status_code in [200, 201]:
                return True

            if response.status_code == 400:
                try:
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
        raise HTTPException(status_code=503, detail="Evolution API não configurada.")
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
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)

            if response.status_code in [200, 201]:
                return True

            # --- CORREÇÃO AQUI ---
            # Tratamento específico para erro 400 (Número inválido)
            if response.status_code == 400:
                try:
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