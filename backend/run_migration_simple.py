"""
Simple migration script - no emoji, ASCII only output.
Run with: python run_migration_simple.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy import text

def migrate():
    db_url = str(engine.url)
    is_mysql = "mysql" in db_url
    print("DB type: MySQL" if is_mysql else "DB type: SQLite")
    print("Connecting to:", db_url[:50] + "...")

    try:
        with engine.connect() as conn:
            if is_mysql:
                sqls = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) DEFAULT NULL",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS client_limit INT NOT NULL DEFAULT 0",
                ]
                for sql in sqls:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        print("OK: " + sql[:80])
                    except Exception as e:
                        print("Skipped (may exist): " + str(e)[:100])

                # Populate feature_flags (disable safe update mode first)
                try:
                    conn.execute(text("SET SQL_SAFE_UPDATES = 0"))
                    conn.execute(text("""
                        UPDATE users
                        SET feature_flags = JSON_OBJECT(
                            'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                            'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                            'resell', TRUE, 'admin', FALSE
                        )
                        WHERE id > 0 AND (feature_flags IS NULL OR CAST(feature_flags AS CHAR) = 'null')
                    """))
                    conn.execute(text("""
                        UPDATE users
                        SET reseller_feature_flags = JSON_OBJECT(
                            'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                            'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                            'resell', TRUE, 'admin', FALSE
                        )
                        WHERE id > 0 AND (reseller_feature_flags IS NULL OR CAST(reseller_feature_flags AS CHAR) = 'null')
                    """))
                    # super_admin always has admin=true
                    conn.execute(text("""
                        UPDATE users
                        SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.admin', CAST(TRUE AS JSON))
                        WHERE id > 0 AND role = 'super_admin'
                    """))
                    conn.execute(text("SET SQL_SAFE_UPDATES = 1"))
                    conn.commit()
                    print("OK: feature_flags and reseller_feature_flags populated!")
                except Exception as e:
                    conn.rollback()
                    print("ERROR populating flags: " + str(e))
            else:
                # SQLite fallback
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
                        print("Added column: " + col)
                    else:
                        print("Column exists: " + col)

                default_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":false}'
                conn.execute(text(f"UPDATE users SET feature_flags = '{default_flags}' WHERE feature_flags IS NULL OR feature_flags = '' OR feature_flags = 'null'"))
                conn.execute(text(f"UPDATE users SET reseller_feature_flags = '{default_flags}' WHERE reseller_feature_flags IS NULL OR reseller_feature_flags = '' OR reseller_feature_flags = 'null'"))
                admin_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":true}'
                conn.execute(text(f"UPDATE users SET feature_flags = '{admin_flags}' WHERE role = 'super_admin'"))
                conn.commit()
                print("OK: feature_flags populated (SQLite)")

        print("\nMigration completed successfully!")
    except Exception as e:
        print("FATAL ERROR: " + str(e))

if __name__ == "__main__":
    migrate()

