# backend/whatsapp_utils.py
import logging
import re
import httpx
from fastapi import HTTPException
from core.config import EVOLUTION_API_URL, EVOLUTION_API_KEY

logger = logging.getLogger("uvicorn")


def evolution_headers():
    return {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }


async def evolution_create_instance(instance_name: str):
    if not EVOLUTION_API_URL:
        return False

    payload = {
        "instanceName": instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS"
    }

    url = f"{EVOLUTION_API_URL}/instance/create"

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
    if not EVOLUTION_API_URL:
        return {}

    async with httpx.AsyncClient() as client:
        try:
            # 1. Busca Estado
            url_state = f"{EVOLUTION_API_URL}/instance/connectionState/{instance_name}"
            response_state = await client.get(url_state, headers=evolution_headers(), timeout=5.0)

            state = "unknown"
            qr_code = None

            if response_state.status_code == 200:
                data = response_state.json()
                state = data.get("instance", {}).get("state") or data.get("state", "unknown")
                qr_code = data.get("qrcode", {}).get("base64") or data.get("qrcode")

            # 2. Tenta conectar se necessário
            if state not in ["open", "connected"] and not qr_code:
                url_connect = f"{EVOLUTION_API_URL}/instance/connect/{instance_name}"
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
    if not EVOLUTION_API_URL: return False
    url = f"{EVOLUTION_API_URL}/instance/delete/{instance_name}"
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(url, headers=evolution_headers(), timeout=5.0)
            return True
        except Exception:
            return False


async def send_whatsapp_notification(number: str, message: str, instance_name: str):
    if not EVOLUTION_API_URL or not instance_name: return False

    clean_number = re.sub(r'\D', '', str(number))
    payload = {
        "number": clean_number,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": message}
    }
    url = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=evolution_headers(), json=payload, timeout=10.0)

            if response.status_code in [200, 201]:
                return True

            # --- CORREÇÃO AQUI ---
            # Tratamento específico para erro 400 (Número inválido)
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    # Verifica se a resposta contém indícios de número inexistente
                    if "exists" in str(error_data) or "number" in str(error_data):
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
            return False

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Exceção envio: {e}")
            return False


def generate_instance_name(user):
    import time
    user_id = user.id if hasattr(user, 'id') else user
    return f"monitor_user_{user_id}_{int(time.time())}"