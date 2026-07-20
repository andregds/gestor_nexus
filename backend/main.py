# backend/main.py
import sys
import os
import time
import httpx
import socket  # <-- NOVO: Necessário para obter o IP
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# Adiciona o diretório `backend` ao sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Imports locais
from core.lifespan import lifespan_manager
from database import Base, engine, SessionLocal
# --- ATUALIZAÇÃO: Importar TODOS os modelos necessários ---
from models import User, Client, MonitoredURL
from routes import auth, users, urls, whatsapp, clients, backup, admin,resellers, messages
from database import engine, Base
import models

# Cria as tabelas no banco de dados, se não existirem
try:
    models.Base.metadata.create_all(bind=engine)
except Exception as _e:
    print(f"[AVISO] Aviso ao criar tabelas: {_e}")

# Migração automática: garante que feature_flags / reseller_feature_flags existem e não são NULL
def _run_startup_migration():
    """
    1. Cria as colunas feature_flags / reseller_feature_flags se não existirem.
    2. Popula valores NULL com os defaults.
    Usa engine.connect() direto para DDL (autocommit implícito no MySQL DDL).
    """
    import json
    from sqlalchemy import text
    _DEFAULT_FLAGS = {
        "dashboard": True, "clients": True, "products": True,
        "whatsapp": True, "telegram": True, "settings": True,
        "resell": True, "admin": False,
    }
    _DEFAULT_PERMS = {
        "can_view_dashboard": True, "can_view_clients": True,
        "can_view_integrations": True, "can_view_settings": True,
    }
    _DEFAULT_PAYMENT_SETTINGS = {
        "gateway_name": "InfinitePay Checkout",
        "bank_name": "",
        "handle": "blue-play",
        "api_base_url": "https://api.checkout.infinitepay.io",
        "links_endpoint": "/links",
        "payment_check_endpoint": "/payment_check",
        "webhook_url": "",
        "redirect_url": "",
        "api_key": "",
        "webhook_secret": "",
        "environment": "production",
        "enabled": False,
    }
    try:
        from database import engine as _eng
        _db_url = str(_eng.url)
        _is_mysql = "mysql" in _db_url

        with _eng.connect() as _conn:
            # --- Passo 1: Garante que as colunas existem ---
            if _is_mysql:
                _alter_stmts = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSON DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS client_limit INT NOT NULL DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_api_settings JSON DEFAULT NULL",
                    "ALTER TABLE products ADD COLUMN IF NOT EXISTS plan_id INT DEFAULT NULL",
                    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS product_id INT DEFAULT NULL",
                    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS payment_status VARCHAR(20) NOT NULL DEFAULT 'pendente'",
                ]
                for _stmt in _alter_stmts:
                    try:
                        _conn.execute(text(_stmt))
                        _conn.commit()
                    except Exception as _e:
                        _conn.rollback()
                        # Ignora silenciosamente erros de coluna duplicada
                        if "1060" not in str(_e) and "Duplicate column" not in str(_e):
                            print(f"[AVISO] DDL ignorado: {_e}")
            else:
                # SQLite: verifica e adiciona manualmente
                _existing = {row[1] for row in _conn.execute(text("PRAGMA table_info(users)"))}
                _sqlite_cols = {
                    "feature_flags": "ALTER TABLE users ADD COLUMN feature_flags TEXT DEFAULT NULL",
                    "reseller_feature_flags": "ALTER TABLE users ADD COLUMN reseller_feature_flags TEXT DEFAULT NULL",
                    "permissions": "ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT NULL",
                    "block_reason": "ALTER TABLE users ADD COLUMN block_reason VARCHAR(255) DEFAULT NULL",
                    "client_limit": "ALTER TABLE users ADD COLUMN client_limit INTEGER DEFAULT 0",
                    "payment_api_settings": "ALTER TABLE users ADD COLUMN payment_api_settings TEXT DEFAULT NULL",
                }
                for _col, _sql in _sqlite_cols.items():
                    if _col not in _existing:
                        try:
                            _conn.execute(text(_sql))
                            _conn.commit()
                        except Exception:
                            _conn.rollback()

                try:
                    _product_existing = {row[1] for row in _conn.execute(text("PRAGMA table_info(products)"))}
                except Exception:
                    _product_existing = set()
                if "plan_id" not in _product_existing:
                    try:
                        _conn.execute(text("ALTER TABLE products ADD COLUMN plan_id INTEGER DEFAULT NULL"))
                        _conn.commit()
                    except Exception:
                        _conn.rollback()

                try:
                    _client_existing = {row[1] for row in _conn.execute(text("PRAGMA table_info(clients)"))}
                except Exception:
                    _client_existing = set()
                if "product_id" not in _client_existing:
                    try:
                        _conn.execute(text("ALTER TABLE clients ADD COLUMN product_id INTEGER DEFAULT NULL"))
                        _conn.commit()
                    except Exception:
                        _conn.rollback()
                if "payment_status" not in _client_existing:
                    try:
                        _conn.execute(text("ALTER TABLE clients ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'pendente'"))
                        _conn.commit()
                    except Exception:
                        _conn.rollback()

            # --- Passo 2: Popula NULLs ---
            try:
                rows = _conn.execute(text(
                    "SELECT id, role, feature_flags, reseller_feature_flags, permissions, payment_api_settings FROM users"
                )).fetchall()
            except Exception as _se:
                print(f"[AVISO] Nao foi possivel ler usuarios para migracao: {_se}")
                return

            _updated = 0
            for row in rows:
                uid, role = row[0], row[1]
                _raw_ff, _raw_rff, _raw_p, _raw_pay = row[2], row[3], row[4], row[5]

                def _pj(v, d):
                    if isinstance(v, dict): return v
                    try: return json.loads(v) if isinstance(v, str) and v.strip() not in ('', 'null') else None
                    except: return None

                ff  = _pj(_raw_ff,  _DEFAULT_FLAGS) or _DEFAULT_FLAGS.copy()
                rff = _pj(_raw_rff, _DEFAULT_FLAGS) or _DEFAULT_FLAGS.copy()
                p   = _pj(_raw_p,   _DEFAULT_PERMS) or _DEFAULT_PERMS.copy()
                pay = _pj(_raw_pay, _DEFAULT_PAYMENT_SETTINGS) or _DEFAULT_PAYMENT_SETTINGS.copy()

                if role == "super_admin":
                    ff["admin"] = True

                try:
                    _conn.execute(
                        text("UPDATE users SET feature_flags=:ff, reseller_feature_flags=:rff, permissions=:p, payment_api_settings=:pay WHERE id=:id"),
                        {"ff": json.dumps(ff), "rff": json.dumps(rff), "p": json.dumps(p), "pay": json.dumps(pay), "id": uid}
                    )
                    _updated += 1
                except Exception as _ue:
                    print(f"[AVISO] Erro ao atualizar usuario {uid}: {_ue}")

            if _updated:
                _conn.commit()
                print(f"[OK] Migracao startup: {_updated} usuario(s) com flags atualizados.")

    except Exception as _me:
        print(f"[AVISO] Migracao startup ignorada (DB indisponivel ou erro): {_me}")

_run_startup_migration()

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

# Monta o diretório de imagens anexas como estático
app.mount("/imagens_anexas", StaticFiles(directory="imagens_anexas"), name="imagens_anexas")

# Adiciona as novas rotas de produtos
from routes import products, categories, plans, features
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(categories.router, prefix="/categories", tags=["Categories"])
app.include_router(plans.router, prefix="/plans", tags=["Plans"])
app.include_router(features.router, prefix="/features", tags=["Features"])

# --- ATUALIZAÇÃO: Importando o gerador de mensagens e configs ---
from core.utils import generate_reminder_message
from core.config import EVOLUTION_API_URL
from whatsapp_utils import evolution_headers
from models import User, Client, MonitoredURL # Garanta que MonitoredURL está aqui
# Cria as tabelas no banco de dados (se não existirem)
Base.metadata.create_all(bind=engine)

# Inclui os routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(users.payment_webhook_router)
app.include_router(urls.router)
app.include_router(whatsapp.router)
app.include_router(clients.router)
app.include_router(backup.router)
app.include_router(admin.router)
app.include_router(resellers.router)
app.include_router(messages.router)

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

        print(f"Encontrados {len(users_list)} usuário(s) para lembretes de cobrança às {now_time}")

        for user in users_list:
            print(f"   Verificando cobranças para: {user.name} (ID: {user.id})")

            if not user.notifications_enabled:
                print(f"      [AVISO] Agendamento DESATIVADO pelo usuario. Pulando.")
                continue

            has_whatsapp = user.whatsapp_connected
            has_telegram = bool(user.telegram_token and user.telegram_chat_id)

            if not has_whatsapp and not has_telegram:
                print(f"      [AVISO] Nenhum canal de notificacao conectado. Pulando.")
                continue

            user_clients = db.query(Client).filter(Client.owner_id == user.id).all()
            if not user_clients:
                continue

            print(f"      Analisando {len(user_clients)} clientes...")

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
                    # Busca mensagem pré-pronta
                    msg = get_predefined_message(days_diff, client.name)
                    if not msg:
                        msg = generate_reminder_message(client.name, days_diff)
                    if not msg:
                        continue

                    print(f"         ENVIANDO MENSAGEM para {client.name} (Motivo: {days_diff} dias)")
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
                                print(f"            WhatsApp enviado com sucesso!")
                            else:
                                print(f"            Erro ao enviar WhatsApp: {response.status_code} - {response.text}")
                        except Exception as e:
                            print(f"            Erro técnico ao enviar WhatsApp: {e}")

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
                                print(f"            Telegram enviado com sucesso!")
                            else:
                                print(f"            Erro ao enviar Telegram: {response.status_code} - {response.text}")
                        except Exception as e:
                            print(f"            Erro técnico ao enviar Telegram: {e}")

                    time.sleep(2) # Pequeno delay para não sobrecarregar as APIs

    except Exception as e:
        print(f"Erro Crítico no Scheduler de Cobranças: {e}")
    finally:
        db.close()


def get_predefined_message(days_diff, client_name):
    # Mapeia days_diff para o tipo de mensagem
    if days_diff < 0:
        msg_type = "vencido"
    elif days_diff == 0:
        msg_type = "vence_1"
    elif days_diff == 1:
        msg_type = "vence_2"
    elif days_diff == 2:
        msg_type = "vence_3"
    elif days_diff == 3:
        msg_type = "vence_4"
    else:
        msg_type = None
    if not msg_type:
        return None
    # Busca a mensagem do tipo correto no banco de dados
    try:
        from models import Message
        db = SessionLocal()
        msg_obj = db.query(Message).filter(Message.message_type == msg_type).first()
        db.close()
        if msg_obj:
            return msg_obj.content.replace("{cliente}", client_name)
    except Exception:
        pass
    return None

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

        print(f"Iniciando verificação de {len(urls_to_check)} URLs ativas...")

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
                    print(f"  [UP] {url_obj.url} -> UP ({http_code})")
                else:
                    status = "DOWN"
                    error_message = f"Status Code {http_code}"
                    print(f"  [DOWN] {url_obj.url} -> DOWN ({http_code})")

            except httpx.RequestError as e:
                error_message = str(e)
                error_type_name = type(e).__name__
                print(f"  [DOWN] {url_obj.url} -> DOWN (Erro de Conexao: {e})")

            except Exception as e:
                error_message = str(e)
                error_type_name = type(e).__name__
                print(f"  [DOWN] {url_obj.url} -> DOWN (Erro Inesperado: {e})")

            finally:
                # --- ACAO MAIS IMPORTANTE: Atualiza o objeto no banco ---
                url_obj.status = status
                url_obj.http_code = http_code
                url_obj.response_time = response_time
                url_obj.ip_address = ip_address
                url_obj.last_check = datetime.now(ZoneInfo("America/Sao_Paulo"))
                url_obj.error = error_message
                url_obj.error_type = error_type_name

                # Salva as alteracoes no banco de dados.
                db.commit()

    except Exception as e:
        print(f"[ERRO CRITICO] Scheduler de URLs: {e}")
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
