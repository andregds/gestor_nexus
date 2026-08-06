# backend/main.py
import os
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from sqlalchemy import inspect, text
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
from reminder_utils import (
    build_client_reminder_message,
    clear_client_reminder_error,
    normalize_reminder_error_message,
    send_client_reminder,
    set_client_reminder_error,
)


def ensure_client_error_columns():
    with engine.begin() as connection:
        inspector = inspect(connection)
        client_columns = {column["name"] for column in inspector.get_columns("clients")} if "clients" in inspector.get_table_names() else set()
        if "clients" not in inspector.get_table_names():
            return
        if "plan_price" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN plan_price FLOAT NULL"))
        if "selected_products" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN selected_products JSON NULL"))
        if "email" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN email VARCHAR(255) NULL"))
        if "reminder_error_message" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN reminder_error_message VARCHAR(500)"))
        if "reminder_error_at" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN reminder_error_at DATETIME"))


def ensure_user_schedule_columns():
    with engine.begin() as connection:
        inspector = inspect(connection)
        user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in inspector.get_table_names() else set()
        if "users" not in inspector.get_table_names():
            return
        if "last_reminder_run_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN last_reminder_run_at DATETIME"))


def ensure_plan_name_index_compatibility():
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "plans" not in inspector.get_table_names():
            return
        if connection.dialect.name == "sqlite":
            return

        obsolete_indexes = set()

        for index in inspector.get_indexes("plans"):
            if index.get("unique") and (index.get("column_names") or []) == ["name"]:
                obsolete_indexes.add(index["name"])

        for constraint in inspector.get_unique_constraints("plans"):
            if (constraint.get("column_names") or []) == ["name"] and constraint.get("name"):
                obsolete_indexes.add(constraint["name"])

        for index_name in obsolete_indexes:
            escaped_index_name = index_name.replace("`", "``")
            connection.execute(text(f"ALTER TABLE plans DROP INDEX `{escaped_index_name}`"))

# Cria as tabelas no banco de dados (se não existirem)
Base.metadata.create_all(bind=engine)
ensure_client_error_columns()
ensure_user_schedule_columns()
ensure_plan_name_index_compatibility()


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
app.include_router(whatsapp.webhook_router)
app.include_router(urls.router)
app.include_router(whatsapp.router)
app.include_router(clients.router)
app.include_router(categories.router)
app.include_router(categories.catalog_router)
app.include_router(plans.router)
app.include_router(plans.catalog_router)
app.include_router(products.router)
app.include_router(products.catalog_router)
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
            has_email = bool((user.payment_api_settings or {}).get("email_settings", {}).get("enabled"))

            if not has_whatsapp and not has_telegram and not has_email:
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
                    msg, template_key, media = build_client_reminder_message(client, user, days_diff)
                elif days_diff < 0 and client.notify_after_expiration:
                    msg, template_key, media = build_client_reminder_message(client, user, days_diff)

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
                            if clear_client_reminder_error(client):
                                db.commit()
                            print(f"            ✅ {channel.title()} enviado com sucesso!")
                        else:
                            if set_client_reminder_error(client, error_detail or f"Falha ao enviar via {channel}."):
                                db.commit()
                            print(f"            ❌ Falha ao enviar via {channel}: {error_detail}")
                    except Exception as e:
                        if set_client_reminder_error(client, normalize_reminder_error_message(e)):
                            db.commit()
                        print(f"            ❌ Erro ao enviar lembrete: {e}")

                    time.sleep(2)  # Delay para evitar spam

            user.last_reminder_run_at = now
            db.commit()

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