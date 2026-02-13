# backend/main.py
import time
import httpx
import socket  # <-- NOVO: Necessário para obter o IP
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

# Imports locais
from core.lifespan import lifespan_manager
from database import Base, engine, SessionLocal
# --- ATUALIZAÇÃO: Importar TODOS os modelos necessários ---
from models import User, Client, MonitoredURL
from routes import auth, users, urls, whatsapp, clients, backup, admin,resellers

# --- ATUALIZAÇÃO: Importando o gerador de mensagens e configs ---
from core.utils import generate_reminder_message
from core.config import EVOLUTION_API_URL
from whatsapp_utils import evolution_headers
from models import User, Client, MonitoredURL # Garanta que MonitoredURL está aqui
# Cria as tabelas no banco de dados (se não existirem)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Monitor DNS API",
    description="API para monitoramento de URLs com notificações WhatsApp.",
    version="2.0.0",
    lifespan=lifespan_manager,
)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclui os routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(urls.router)
app.include_router(whatsapp.router)
app.include_router(clients.router)
app.include_router(backup.router)
app.include_router(admin.router)
app.include_router(resellers.router)

# =================================================================
# TAREFA 1: VERIFICADOR DE LEMBRETES DE COBRANÇA (SEU CÓDIGO ATUAL)
# =================================================================

def check_and_send_reminders():
    """
    Roda a cada minuto para enviar lembretes de cobrança de clientes.
    """
    db = SessionLocal()
    try:
        tz_brazil = ZoneInfo("America/Sao_Paulo")
        now = datetime.now(tz_brazil)
        now_time = now.strftime("%H:%M")
        today = now.date()

        users_list = db.query(User).filter(User.notification_time == now_time).all()

        if not users_list:
            return

        print(f"🔔 Encontrados {len(users_list)} usuário(s) para lembretes de cobrança às {now_time}")

        for user in users_list:
            print(f"   👤 Verificando cobranças para: {user.name} (ID: {user.id})")

            if not user.notifications_enabled:
                print(f"      ⚠️ Agendamento DESATIVADO pelo usuário. Pulando.")
                continue

            has_whatsapp = user.whatsapp_connected
            has_telegram = bool(user.telegram_token and user.telegram_chat_id)

            if not has_whatsapp and not has_telegram:
                print(f"      ⚠️ Nenhum canal de notificação conectado. Pulando.")
                continue

            user_clients = db.query(Client).filter(Client.owner_id == user.id).all()
            if not user_clients:
                continue

            print(f"      📂 Analisando {len(user_clients)} clientes...")

            for client in user_clients:
                if not client.reminder_enabled:
                    continue

                days_diff = (client.expiration_date - today).days

                try:
                    days_alert_threshold = int(client.reminder_days_before)
                except (ValueError, TypeError):
                    days_alert_threshold = 3

                should_send = False
                if 0 <= days_diff <= days_alert_threshold:
                    should_send = True
                elif days_diff < 0 and client.notify_after_expiration:
                    should_send = True

                if should_send:
                    msg = generate_reminder_message(client.name, days_diff)
                    if not msg:
                        continue

                    print(f"         🚀 ENVIANDO MENSAGEM para {client.name} (Motivo: {days_diff} dias)")
                    channel = client.notification_channel or "whatsapp"

                    # --- ENVIO VIA WHATSAPP (SÍNCRONO) ---
                    if channel == "whatsapp" and has_whatsapp and client.whatsapp:
                        try:
                            payload = {
                                "number": client.whatsapp,
                                "options": {"delay": 1200, "presence": "composing"},
                                "textMessage": {"text": msg}
                            }
                            url = f"{EVOLUTION_API_URL}/message/sendText/{user.whatsapp_instance}"
                            response = httpx.post(url, headers=evolution_headers(), json=payload, timeout=10.0)
                            if response.status_code in [200, 201]:
                                print(f"            ✅ WhatsApp enviado com sucesso!")
                            else:
                                print(f"            ❌ Erro ao enviar WhatsApp: {response.status_code} - {response.text}")
                        except Exception as e:
                            print(f"            ❌ Erro técnico ao enviar WhatsApp: {e}")

                    # --- ENVIO VIA TELEGRAM (SÍNCRONO) ---
                    elif channel == "telegram" and has_telegram:
                        try:
                            telegram_url = f"https://api.telegram.org/bot{user.telegram_token}/sendMessage"
                            payload = {
                                "chat_id": user.telegram_chat_id,
                                "text": f"🔔 *Lembrete Cliente: {client.name}*\n\n{msg}",
                                "parse_mode": "Markdown"
                            }
                            response = httpx.post(telegram_url, json=payload, timeout=10.0)
                            if response.status_code == 200:
                                print(f"            ✅ Telegram enviado com sucesso!")
                            else:
                                print(f"            ❌ Erro ao enviar Telegram: {response.status_code} - {response.text}")
                        except Exception as e:
                            print(f"            ❌ Erro técnico ao enviar Telegram: {e}")

                    time.sleep(2) # Pequeno delay para não sobrecarregar as APIs

    except Exception as e:
        print(f"❌ Erro Crítico no Scheduler de Cobranças: {e}")
    finally:
        db.close()


# =================================================================
# TAREFA 2: MONITOR DE URLS (NOVO CÓDIGO PARA CORRIGIR O PAINEL)
# =================================================================

def check_monitored_urls():
    """
    Roda a cada minuto para verificar o status das URLs monitoradas.
    Esta função corrige o painel que não atualizava.
    """
    db = SessionLocal()
    try:
        urls_to_check = db.query(MonitoredURL).filter(MonitoredURL.is_active == True).all()
        if not urls_to_check:
            return  # Sai se não houver URLs ativas para checar

        print(f"🔍 Iniciando verificação de {len(urls_to_check)} URLs ativas...")

        for url_obj in urls_to_check:
            status = "DOWN"
            http_code = None
            response_time = None
            ip_address = None
            error_message = None
            error_type_name = None

            try:
                with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                    start_time = time.time()
                    response = client.get(url_obj.url)
                    end_time = time.time()

                response_time = (end_time - start_time) * 1000  # em ms
                http_code = response.status_code

                hostname = httpx.URL(url_obj.url).host
                ip_address = socket.gethostbyname(hostname)

                if 200 <= http_code < 400:
                    status = "UP"
                    print(f"  ✅ {url_obj.url} -> UP ({http_code})")
                else:
                    status = "DOWN"
                    error_message = f"Status Code {http_code}"
                    print(f"  ❌ {url_obj.url} -> DOWN ({http_code})")

            except httpx.RequestError as e:
                error_message = str(e)
                error_type_name = type(e).__name__
                print(f"  ❌ {url_obj.url} -> DOWN (Erro de Conexão: {e})")

            except Exception as e:
                error_message = str(e)
                error_type_name = type(e).__name__
                print(f"  ❌ {url_obj.url} -> DOWN (Erro Inesperado: {e})")

            finally:
                # --- AÇÃO MAIS IMPORTANTE: Atualiza o objeto no banco ---
                url_obj.status = status
                url_obj.http_code = http_code
                url_obj.response_time = response_time
                url_obj.ip_address = ip_address
                url_obj.last_check = datetime.now(ZoneInfo("America/Sao_Paulo"))
                url_obj.error = error_message
                url_obj.error_type = error_type_name

                # Salva as alterações no banco de dados. É ISSO que atualiza o site!
                db.commit()

    except Exception as e:
        print(f"🔥 Erro Crítico no Scheduler de URLs: {e}")
    finally:
        db.close()


# ==========================================
# INICIALIZAÇÃO DO AGENDADOR (SCHEDULER)
# ==========================================

# Inicializa o Scheduler em segundo plano
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

# TAREFA 1: Envio de lembretes de cobrança (a cada minuto)
scheduler.add_job(check_and_send_reminders, 'interval', minutes=1, id='job_reminders')

# TAREFA 2: Monitoramento de URLs (a cada minuto)
scheduler.add_job(check_monitored_urls, 'interval', minutes=1, id='job_url_monitor')

# Inicia o agendador
scheduler.start()


@app.get("/", tags=["Geral"], include_in_schema=False)
def root():
    return {
        "app": "Nexus Monitor API",
        "status": "online",
        "version": "2.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
