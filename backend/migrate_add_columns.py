#!/usr/bin/env python3
"""
Script de migracao: adiciona colunas ausentes na tabela users (MySQL).
Execute na pasta backend:
    python migrate_add_columns.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import text
from database import engine
DEFAULT_FLAGS = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": false}'
DEFAULT_PERMS = '{"can_view_dashboard": true, "can_view_clients": true, "can_view_integrations": true, "can_view_settings": true}'
def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0
def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        print(f"  Adicionando coluna: {table}.{column}")
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    else:
        print(f"  Coluna ja existe: {table}.{column}")
def run():
    is_mysql = not str(engine.url).startswith("sqlite")
    if not is_mysql:
        print("Banco SQLite detectado - migracao nao necessaria aqui.")
        return
    print("Iniciando migracao do banco MySQL...")
    with engine.begin() as conn:
        add_column_if_missing(conn, "users", "feature_flags",           "JSON DEFAULT NULL")
        add_column_if_missing(conn, "users", "reseller_feature_flags",  "JSON DEFAULT NULL")
        add_column_if_missing(conn, "users", "permissions",             "JSON DEFAULT NULL")
        add_column_if_missing(conn, "users", "block_reason",            "VARCHAR(255) DEFAULT NULL")
        add_column_if_missing(conn, "users", "client_limit",            "INT NOT NULL DEFAULT 0")
        add_column_if_missing(conn, "users", "owner_id",                "INT DEFAULT NULL")
        add_column_if_missing(conn, "users", "telegram_token",          "VARCHAR(255) DEFAULT NULL")
        add_column_if_missing(conn, "users", "telegram_chat_id",        "VARCHAR(100) DEFAULT NULL")
        add_column_if_missing(conn, "users", "notification_channel",    "VARCHAR(50) DEFAULT 'whatsapp'")
        add_column_if_missing(conn, "users", "notifications_enabled",   "TINYINT(1) NOT NULL DEFAULT 1")
        add_column_if_missing(conn, "users", "notify_when_down",        "TINYINT(1) NOT NULL DEFAULT 1")
        add_column_if_missing(conn, "users", "notify_when_up",          "TINYINT(1) NOT NULL DEFAULT 1")
        add_column_if_missing(conn, "users", "notify_when_slow",        "TINYINT(1) NOT NULL DEFAULT 0")
        add_column_if_missing(conn, "users", "notification_time",       "VARCHAR(10) DEFAULT '09:00'")
        add_column_if_missing(conn, "users", "whatsapp_instance",       "VARCHAR(100) DEFAULT NULL")
        add_column_if_missing(conn, "users", "whatsapp_apikey",         "VARCHAR(255) DEFAULT NULL")
        add_column_if_missing(conn, "users", "is_active",               "TINYINT(1) NOT NULL DEFAULT 1")
        add_column_if_missing(conn, "products", "plan_id",              "INT DEFAULT NULL")
        conn.execute(text("UPDATE users SET feature_flags = :f WHERE feature_flags IS NULL"), {"f": DEFAULT_FLAGS})
        conn.execute(text("UPDATE users SET feature_flags = JSON_SET(feature_flags, '$.admin', TRUE) WHERE role = 'super_admin'"))
        conn.execute(text("UPDATE users SET reseller_feature_flags = :f WHERE reseller_feature_flags IS NULL"), {"f": DEFAULT_FLAGS})
        conn.execute(text("UPDATE users SET permissions = :p WHERE permissions IS NULL"), {"p": DEFAULT_PERMS})
    from models import Base
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("Migracao concluida!")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, email, role, feature_flags FROM users")).fetchall()
        for r in rows:
            print(f"ID={r[0]}, email={r[1]}, role={r[2]}, flags={r[3]}")
if __name__ == "__main__":
    run()