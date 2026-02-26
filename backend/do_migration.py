"""
Migration script that writes output to a log file.
Run: python do_migration.py
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration_log.txt")

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg, flush=True)

log("=== Starting migration ===")

try:
    from dotenv import load_dotenv
    load_dotenv()
    log("dotenv loaded")

    from database import engine
    log("database engine imported")
    
    from sqlalchemy import text

    db_url = str(engine.url)
    log("DB URL: " + db_url[:60])
    is_mysql = "mysql" in db_url

    with engine.connect() as conn:
        log("Connected to database!")
        
        if is_mysql:
            sqls = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
            ]
            for sql in sqls:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    log("OK: " + sql[:80])
                except Exception as e:
                    log("Skip: " + str(e)[:100])

            # Populate feature_flags
            try:
                conn.execute(text("SET SQL_SAFE_UPDATES = 0"))
                result = conn.execute(text("""
                    UPDATE users
                    SET feature_flags = JSON_OBJECT(
                        'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                        'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                        'resell', TRUE, 'admin', FALSE
                    )
                    WHERE id > 0 AND (feature_flags IS NULL OR CAST(feature_flags AS CHAR) = 'null')
                """))
                log("Rows updated (feature_flags): " + str(result.rowcount))
                
                result2 = conn.execute(text("""
                    UPDATE users
                    SET reseller_feature_flags = JSON_OBJECT(
                        'dashboard', TRUE, 'clients', TRUE, 'products', TRUE,
                        'whatsapp', TRUE, 'telegram', TRUE, 'settings', TRUE,
                        'resell', TRUE, 'admin', FALSE
                    )
                    WHERE id > 0 AND (reseller_feature_flags IS NULL OR CAST(reseller_feature_flags AS CHAR) = 'null')
                """))
                log("Rows updated (reseller_feature_flags): " + str(result2.rowcount))

                conn.execute(text("""
                    UPDATE users
                    SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.admin', CAST(TRUE AS JSON))
                    WHERE id > 0 AND role = 'super_admin'
                """))
                log("super_admin admin flag set")
                
                conn.execute(text("SET SQL_SAFE_UPDATES = 1"))
                conn.commit()
                log("Commit OK!")
            except Exception as e:
                log("ERROR populating flags: " + str(e))
                conn.rollback()
        else:
            log("SQLite DB detected")

    log("=== Migration completed! ===")

except Exception as e:
    log("FATAL ERROR: " + str(e))
    import traceback
    log(traceback.format_exc())

