#!/usr/bin/env python3
"""
Script de migração: adiciona colunas feature_flags e reseller_feature_flags
na tabela users do banco de dados MySQL.

Uso:
    cd backend
    python ../migrate_add_feature_flags.py
"""
import sys
import os
import json

# Garante que o diretório do backend está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database import engine
from sqlalchemy import text

DEFAULT_FLAGS = json.dumps({
    "dashboard": True,
    "clients": True,
    "products": True,
    "whatsapp": True,
    "telegram": True,
    "settings": True,
    "resell": True,
    "admin": False,
})

DEFAULT_FLAGS_ADMIN = json.dumps({
    "dashboard": True,
    "clients": True,
    "products": True,
    "whatsapp": True,
    "telegram": True,
    "settings": True,
    "resell": True,
    "admin": True,
})

def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0

def run_migration():
    with engine.connect() as conn:
        # 1. Adicionar feature_flags
        if not column_exists(conn, "users", "feature_flags"):
            print("➕ Adicionando coluna feature_flags...")
            conn.execute(text("ALTER TABLE users ADD COLUMN feature_flags JSON DEFAULT NULL"))
            conn.commit()
            print("✅ Coluna feature_flags adicionada.")
        else:
            print("ℹ️  Coluna feature_flags já existe.")

        # 2. Adicionar reseller_feature_flags
        if not column_exists(conn, "users", "reseller_feature_flags"):
            print("➕ Adicionando coluna reseller_feature_flags...")
            conn.execute(text("ALTER TABLE users ADD COLUMN reseller_feature_flags JSON DEFAULT NULL"))
            conn.commit()
            print("✅ Coluna reseller_feature_flags adicionada.")
        else:
            print("ℹ️  Coluna reseller_feature_flags já existe.")

        # 3. Preencher NULLs em feature_flags (usuários comuns)
        print("🔄 Preenchendo feature_flags NULL para usuários comuns...")
        conn.execute(text(
            f"UPDATE users SET feature_flags = :flags WHERE feature_flags IS NULL AND role != 'super_admin'"
        ), {"flags": DEFAULT_FLAGS})
        conn.commit()

        # 4. Preencher NULLs em feature_flags (super_admin)
        print("🔄 Preenchendo feature_flags para super_admin (com admin=True)...")
        conn.execute(text(
            f"UPDATE users SET feature_flags = :flags WHERE feature_flags IS NULL AND role = 'super_admin'"
        ), {"flags": DEFAULT_FLAGS_ADMIN})
        conn.commit()

        # 5. Garantir admin=True para super_admin existentes
        print("🔄 Garantindo admin=True para super_admins...")
        conn.execute(text(
            "UPDATE users SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.admin', true) "
            "WHERE role = 'super_admin'"
        ))
        conn.commit()

        # 6. Preencher NULLs em reseller_feature_flags
        print("🔄 Preenchendo reseller_feature_flags NULL...")
        conn.execute(text(
            f"UPDATE users SET reseller_feature_flags = :flags WHERE reseller_feature_flags IS NULL"
        ), {"flags": DEFAULT_FLAGS})
        conn.commit()

        print("\n✅ Migração concluída com sucesso!")

        # Verificação
        result = conn.execute(text("SELECT id, email, role, feature_flags FROM users"))
        rows = result.fetchall()
        print(f"\n📊 Usuários no banco ({len(rows)} total):")
        for row in rows:
            print(f"  ID={row[0]}, email={row[1]}, role={row[2]}, feature_flags={row[3]}")

if __name__ == "__main__":
    run_migration()

