# backend/monitor.py
import asyncio
import socket
from datetime import datetime
from sqlalchemy.orm import Session
import requests
import os
from dotenv import load_dotenv

from models import User, MonitoredURL
from whatsapp_utils import send_whatsapp_notification
# Importação do utilitário do Telegram
from telegram_utils import send_telegram_message

load_dotenv()

# Configurações do monitor
TIMEOUT_SECONDS = 10
SLOW_RESPONSE_THRESHOLD = 3.0


def check_dns(url: str) -> dict:
    """Verifica DNS + HTTP da URL completa."""
    try:
        clean_url = url.replace("http://", "").replace("https://", "")
        host = clean_url.split("/")[0].split(":")[0]

        try:
            ip_address = socket.gethostbyname(host)
        except socket.gaierror:
            return {
                "status": "DOWN",
                "ip_address": None,
                "http_code": None,
                "response_time": 0,
                "error": "Falha na resolução DNS",
                "error_type": "DNS_ERROR",
            }

        import time
        start = time.time()

        try:
            # Desabilita avisos de certificado SSL inseguro para monitoramento
            requests.packages.urllib3.disable_warnings()

            response = requests.get(
                url,
                timeout=TIMEOUT_SECONDS,
                allow_redirects=True,
                verify=False
            )
            response_time = time.time() - start
            http_code = response.status_code

            if 200 <= http_code < 300:
                if response_time > SLOW_RESPONSE_THRESHOLD:
                    status = "WARNING"
                else:
                    status = "UP"
            elif 300 <= http_code < 400:
                status = "WARNING"
            else:
                status = "DOWN"

            return {
                "status": status,
                "ip_address": ip_address,
                "http_code": http_code,
                "response_time": response_time,
                "error": None,
                "error_type": None,
            }

        except requests.exceptions.Timeout:
            return {
                "status": "DOWN",
                "ip_address": ip_address,
                "http_code": None,
                "response_time": TIMEOUT_SECONDS,
                "error": "Tempo limite excedido",
                "error_type": "TIMEOUT",
            }

        except requests.exceptions.ConnectionError:
            return {
                "status": "DOWN",
                "ip_address": ip_address,
                "http_code": None,
                "response_time": 0,
                "error": "Erro de conexão",
                "error_type": "CONNECTION_ERROR",
            }

        except requests.exceptions.RequestException as e:
            return {
                "status": "DOWN",
                "ip_address": ip_address,
                "http_code": None,
                "response_time": 0,
                "error": str(e),
                "error_type": "HTTP_ERROR",
            }

    except Exception as e:
        return {
            "status": "DOWN",
            "ip_address": None,
            "http_code": None,
            "response_time": 0,
            "error": str(e),
            "error_type": "UNKNOWN_ERROR",
        }


async def monitor_urls(db: Session):
    """Verifica o status de todas as URLs monitoradas e envia notificações."""
    try:
        urls_to_monitor = db.query(MonitoredURL).filter(MonitoredURL.is_active == True).all()

        for url_obj in urls_to_monitor:
            result = check_dns(url_obj.url)

            previous_status = url_obj.status

            # Atualiza o objeto com os novos dados
            url_obj.status = result["status"]
            url_obj.ip_address = result["ip_address"]
            url_obj.http_code = result["http_code"]
            url_obj.last_check = datetime.now()
            url_obj.response_time = result["response_time"]
            url_obj.error = result["error"]
            url_obj.error_type = result["error_type"]

            db.add(url_obj)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {url_obj.url} -> {url_obj.status}")

            # Lógica de notificação
            if url_obj.status != previous_status and url_obj.owner:
                user = url_obj.owner

                # Verifica se notificações globais estão ativas
                if not user.notifications_enabled:
                    continue

                # Verifica flags específicas de notificação
                should_notify = False
                msg_type = ""
                emoji = ""

                # Usa getattr para evitar erro caso o campo não exista no modelo antigo em memória,
                # mas idealmente o modelo User já tem esses campos.
                notify_down = getattr(user, 'notify_when_down', True)
                notify_up = getattr(user, 'notify_when_up', True)
                notify_slow = getattr(user, 'notify_when_slow', False)

                if url_obj.status == "DOWN" and notify_down:
                    should_notify = True
                    msg_type = "Serviço OFFLINE"
                    emoji = "🔴"
                elif url_obj.status == "UP" and previous_status != "UP" and notify_up:
                    should_notify = True
                    msg_type = "Serviço ONLINE"
                    emoji = "🟢"
                elif url_obj.status == "WARNING" and notify_slow:
                    should_notify = True
                    msg_type = "Lentidão Detectada"
                    emoji = "⚠️"

                if should_notify:
                    # Monta mensagem
                    msg = (
                        f"{emoji} *Monitor DNS - {msg_type}*\n\n"
                        f"🔗 *URL:* {url_obj.url}\n"
                        f"📊 *Status:* {url_obj.status}\n"
                        f"⏱️ *Tempo:* {url_obj.response_time:.2f}s\n"
                    )
                    if url_obj.error:
                        msg += f"❌ *Erro:* {url_obj.error}"

                    # 1. Envia WhatsApp (se configurado)
                    if user.whatsapp_number and user.whatsapp_instance:
                        try:
                            await send_whatsapp_notification(
                                user.whatsapp_number,
                                msg,
                                user.whatsapp_instance
                            )
                        except Exception as e:
                            print(f"Erro ao enviar WhatsApp: {e}")

                    # 2. Envia Telegram (se configurado)
                    if user.telegram_token and user.telegram_chat_id:
                        try:
                            await send_telegram_message(
                                user.telegram_token,
                                user.telegram_chat_id,
                                msg
                            )
                        except Exception as e:
                            print(f"Erro ao enviar Telegram: {e}")

            db.commit()
            db.refresh(url_obj)

    except Exception as e:
        print(f"❌ Erro no monitoramento: {str(e)}")
        db.rollback()


async def start_monitoring(db_session_factory):
    """Inicia loop de monitoramento."""
    from database import SessionLocal
    print("🚀 Iniciando monitoramento de URLs...")
    while True:
        db = SessionLocal()
        try:
            await monitor_urls(db)
        except Exception as e:
            print(f"Erro crítico no loop: {e}")
        finally:
            db.close()
        await asyncio.sleep(30)