# backend/main.py
import os
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

# Imports locais
from core.lifespan import lifespan_manager
from database import Base, engine, SessionLocal
from models import User, Client
from routes import admin, auth, categories, clients, plans, products, urls, users, whatsapp

# Utilitários de envio
from reminder_utils import build_client_reminder_message, send_client_reminder

# Cria as tabelas no banco de dados (se não existirem)
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Ciclo de vida da aplicacao.

    Inicia o scheduler de cobrancas aqui (e nao no import do modulo) para evitar
    execucao duplicada quando o Uvicorn roda com reload/multiplos workers, o que
    causaria envio duplicado de lembretes. Delega o restante ao lifespan_manager
    (monitoramento de URLs).
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_send_reminders, "interval", minutes=1)
    scheduler.start()
    app.state.scheduler = scheduler
    print("[startup] Scheduler de cobrancas iniciado.")
    try:
        async with lifespan_manager(app):
            yield
    finally:
        scheduler.shutdown(wait=False)
        print("[shutdown] Scheduler de cobrancas encerrado.")


app = FastAPI(
    title="Monitor DNS API",
    description="API para monitoramento de URLs com notificações WhatsApp.",
    version="2.0.0",
    lifespan=app_lifespan,
)

# Configuração CORS
# allow_credentials=False: a autenticação usa Bearer token (OAuth2), nao cookies.
# A combinacao allow_origins=["*"] + allow_credentials=True e invalida pela spec
# CORS e rejeitada pelos navegadores (achado OWASP). Para habilitar credenciais,
# defina origens explicitas via variavel de ambiente.
_cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
_allow_origins = ["*"] if _cors_origins_env in ("", "*") else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
_allow_credentials = _allow_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclui os routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(users.payment_webhook_router)
app.include_router(urls.router)
app.include_router(whatsapp.router)
app.include_router(clients.router)
app.include_router(categories.router)
app.include_router(plans.router)
app.include_router(products.router)
app.include_router(admin.router)


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
                media = None

                # --- NOVA LÓGICA DINÂMICA ---

                if 0 <= days_diff <= days_alert_threshold:
                    msg, _, media = build_client_reminder_message(client, user, days_diff)
                elif days_diff < 0 and client.notify_after_expiration:
                    msg, _, media = build_client_reminder_message(client, user, days_diff)

                # Se encontrou uma regra válida, envia
                if msg:
                    print(f"         🚀 ENVIANDO MENSAGEM para {client.name} (Motivo: {days_diff} dias)")
                    try:
                        success, channel, error_detail = asyncio.run(
                            send_client_reminder(
                                user,
                                client,
                                msg,
                                media=media,
                                telegram_prefix=f"🔔 *Lembrete Cliente: {client.name}*",
                            )
                        )
                        if success:
                            print(f"            ✅ {channel.title()} enviado com sucesso!")
                        else:
                            print(f"            ❌ Falha ao enviar via {channel}: {error_detail}")
                    except Exception as e:
                        print(f"            ❌ Erro ao enviar lembrete: {e}")

                    time.sleep(2)  # Delay para evitar spam

    except Exception as e:
        print(f"❌ Erro Crítico no Scheduler: {e}")
    finally:
        db.close()


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