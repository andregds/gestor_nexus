"""
Script de migração para adicionar colunas feature_flags e reseller_feature_flags à tabela users.
Execute com: python migrate_feature_flags.py
"""
import sys
import os

# Garante que os imports do projeto funcionem
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy import text

def migrate():
    db_url = str(engine.url)
    is_mysql = "mysql" in db_url

    with engine.connect() as conn:
        if is_mysql:
            # ---- MySQL ----
            sqls = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS client_limit INT NOT NULL DEFAULT 0",
            ]
            for sql in sqls:
                try:
                    conn.execute(text(sql))
                    print(f"✅ OK: {sql[:80]}")
                except Exception as e:
                    print(f"⚠️  Ignorado (pode já existir): {e}")

            # Popula feature_flags com defaults para linhas NULL
            try:
                conn.execute(text("""
                    UPDATE users
                    SET feature_flags = JSON_OBJECT(
                        'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                        'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                        'resell', TRUE, 'admin', FALSE
                    )
                    WHERE feature_flags IS NULL OR CAST(feature_flags AS CHAR) = 'null'
                """))
                conn.execute(text("""
                    UPDATE users
                    SET reseller_feature_flags = JSON_OBJECT(
                        'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                        'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                        'resell', TRUE, 'admin', FALSE
                    )
                    WHERE reseller_feature_flags IS NULL OR CAST(reseller_feature_flags AS CHAR) = 'null'
                """))
                # super_admin sempre tem admin=true
                conn.execute(text("""
                    UPDATE users
                    SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.admin', CAST(TRUE AS JSON))
                    WHERE role = 'super_admin'
                """))
                conn.commit()
                print("✅ feature_flags e reseller_feature_flags populados com sucesso!")
            except Exception as e:
                conn.rollback()
                print(f"❌ Erro ao popular flags: {e}")
        else:
            # ---- SQLite (desenvolvimento local) ----
            # SQLite não tem ADD COLUMN IF NOT EXISTS, precisamos checar antes
            existing = set()
            result = conn.execute(text("PRAGMA table_info(users)"))
            for row in result:
                existing.add(row[1])

            needed = {
                "feature_flags": "ALTER TABLE users ADD COLUMN feature_flags TEXT DEFAULT NULL",
                "reseller_feature_flags": "ALTER TABLE users ADD COLUMN reseller_feature_flags TEXT DEFAULT NULL",
                "block_reason": "ALTER TABLE users ADD COLUMN block_reason VARCHAR(255) DEFAULT NULL",
                "client_limit": "ALTER TABLE users ADD COLUMN client_limit INTEGER DEFAULT 0",
            }
            for col, sql in needed.items():
                if col not in existing:
                    conn.execute(text(sql))
                    print(f"✅ Coluna '{col}' adicionada (SQLite)")
                else:
                    print(f"ℹ️  Coluna '{col}' já existe (SQLite)")

            # Popula com JSON padrão
            default_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":false}'
            conn.execute(text(f"""
                UPDATE users SET feature_flags = '{default_flags}'
                WHERE feature_flags IS NULL OR feature_flags = '' OR feature_flags = 'null'
            """))
            conn.execute(text(f"""
                UPDATE users SET reseller_feature_flags = '{default_flags}'
                WHERE reseller_feature_flags IS NULL OR reseller_feature_flags = '' OR reseller_feature_flags = 'null'
            """))
            admin_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":true}'
            conn.execute(text(f"""
                UPDATE users SET feature_flags = '{admin_flags}'
                WHERE role = 'super_admin'
            """))
            conn.commit()
            print("✅ feature_flags e reseller_feature_flags populados (SQLite)")

    print("\n🎉 Migração concluída com sucesso!")

if __name__ == "__main__":
    migrate()

