# backend/main.py
import time
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

# Imports locais
from core.lifespan import lifespan_manager
from database import Base, engine, SessionLocal
from models import User, Client
from routes import auth, users, urls, whatsapp, clients

# Utilitários de envio
from telegram_utils import send_telegram_message
from whatsapp_utils import send_whatsapp_notification

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


# ==========================================
# LÓGICA DO AGENDADOR (SCHEDULER)
# ==========================================

def check_and_send_reminders():
    """
    Roda a cada minuto.
    Verifica se há usuários configurados para receber notificações neste minuto exato.
    """
    # Cria uma nova sessão de banco de dados para esta thread
    db = SessionLocal()
    try:
        now = datetime.now()
        now_time = now.strftime("%H:%M")

        # --- DEBUG: Mostra que o scheduler está vivo ---
        # print(f"⏰ Scheduler Check: {now} (Procurando agendamentos para {now_time})")

        # 1. Busca usuários que configuraram este horário exato
        users_list = db.query(User).filter(User.notification_time == now_time).all()

        if users_list:
            print(f"🔔 Encontrados {len(users_list)} usuário(s) agendados para {now_time}")

        for user in users_list:
            print(f"   👤 Verificando usuário: {user.name} (ID: {user.id})")

            # Verifica se o agendamento está ativado
            if not user.notifications_enabled:
                print(f"      ⚠️ Agendamento DESATIVADO pelo usuário. Pulando.")
                continue

            # Verifica canais
            has_whatsapp = user.whatsapp_connected
            has_telegram = bool(user.telegram_token and user.telegram_chat_id)

            if not has_whatsapp and not has_telegram:
                print(f"      ⚠️ Nenhum canal de notificação conectado. Pulando.")
                continue

            # 2. Busca clientes deste usuário
            user_clients = db.query(Client).filter(Client.owner_id == user.id).all()
            today = datetime.now().date()

            print(f"      📂 Analisando {len(user_clients)} clientes...")

            for client in user_clients:
                if not client.reminder_enabled:
                    continue

                # Calcula dias para vencer
                days_diff = (client.expiration_date - today).days

                # --- LÓGICA DA FLAG DE DIAS ---
                # Tenta converter a configuração de dias do cliente para inteiro (padrão 3 se falhar)
                try:
                    days_alert_threshold = int(client.reminder_days_before)
                except (ValueError, TypeError):
                    days_alert_threshold = 3

                msg = ""

                # --- NOVA LÓGICA DINÂMICA ---

                # 1. Lógica de Vencimento Próximo (Intervalo de 0 até X dias configurados)
                # Ex: Se configurou 5, entra aqui se faltar 5, 4, 3, 2, 1 ou 0 dias.
                if 0 <= days_diff <= days_alert_threshold:
                    if days_diff == 0:
                        msg = f"Olá {client.name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
                    elif days_diff == 1:
                        msg = f"Olá {client.name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
                    else:
                        msg = f"Olá {client.name}! 📅 Sua assinatura vence em {days_diff} dias. Evite bloqueios!"

                # 2. Lógica de Vencido (Qualquer dia negativo)
                # Envia se estiver vencido há 1 ou mais dias, desde que a opção esteja ativa
                elif days_diff < 0 and client.notify_after_expiration:
                    days_overdue = abs(days_diff) # Converte -1 para 1, -5 para 5, etc.
                    msg = f"Olá {client.name}. ❌ Sua assinatura venceu há {days_overdue} dias. Entre em contato para reativar."

                # Se encontrou uma regra válida, envia
                if msg:
                    print(f"         🚀 ENVIANDO MENSAGEM para {client.name} (Motivo: {days_diff} dias)")
                    channel = client.notification_channel or "whatsapp"

                    # --- ENVIO VIA WHATSAPP ---
                    if channel == "whatsapp" and has_whatsapp:
                        if client.whatsapp:
                            try:
                                asyncio.run(send_whatsapp_notification(
                                    number=client.whatsapp,
                                    message=msg,
                                    instance_name=user.whatsapp_instance
                                ))
                                print(f"            ✅ WhatsApp enviado com sucesso!")
                            except Exception as e:
                                print(f"            ❌ Erro ao enviar WhatsApp: {e}")

                    # --- ENVIO VIA TELEGRAM ---
                    elif channel == "telegram" and has_telegram:
                        try:
                            asyncio.run(send_telegram_message(
                                token=user.telegram_token,
                                chat_id=user.telegram_chat_id,
                                message=f"🔔 *Lembrete Cliente: {client.name}*\n\n{msg}"
                            ))
                            print(f"            ✅ Telegram enviado com sucesso!")
                        except Exception as e:
                            print(f"            ❌ Erro ao enviar Telegram: {e}")

                    time.sleep(2)  # Delay para evitar spam

    except Exception as e:
        print(f"❌ Erro Crítico no Scheduler: {e}")
    finally:
        db.close()


# Inicializa o Scheduler em segundo plano
scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_reminders, 'interval', minutes=1)
scheduler.start()


@app.get("/", tags=["Geral"])
def root():
    return {
        "app": "Monitor DNS com Notificações WhatsApp",
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