"""
Fix migration for MariaDB - set super_admin feature_flags.admin = true
and ensure all users have valid feature_flags.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy import text

log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fix_log.txt")

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

log("=== Fix migration start ===")

try:
    with engine.connect() as conn:
        conn.execute(text("SET SQL_SAFE_UPDATES = 0"))

        # Check what's in the DB
        result = conn.execute(text("SELECT id, role, feature_flags, reseller_feature_flags FROM users LIMIT 10"))
        for row in result:
            log(f"User id={row[0]} role={row[1]} ff={str(row[2])[:80]} rff={str(row[3])[:80]}")

        # Fill NULL feature_flags
        r1 = conn.execute(text("""
            UPDATE users
            SET feature_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":false}'
            WHERE id > 0 AND (feature_flags IS NULL OR feature_flags = 'null' OR CAST(feature_flags AS CHAR) = '')
        """))
        log("feature_flags filled: " + str(r1.rowcount))

        r2 = conn.execute(text("""
            UPDATE users
            SET reseller_feature_flags = '{"dashboard":true,"clients":true,"products":true,"whatsapp":true,"telegram":true,"settings":true,"resell":true,"admin":false}'
            WHERE id > 0 AND (reseller_feature_flags IS NULL OR reseller_feature_flags = 'null' OR CAST(reseller_feature_flags AS CHAR) = '')
        """))
        log("reseller_feature_flags filled: " + str(r2.rowcount))

        # Set admin=true for super_admin using JSON_SET with MariaDB compatible syntax
        # MariaDB JSON_SET with true as a JSON value
        r3 = conn.execute(text("""
            UPDATE users
            SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.admin', true)
            WHERE id > 0 AND role = 'super_admin'
        """))
        log("super_admin admin=true set: " + str(r3.rowcount))

        conn.execute(text("SET SQL_SAFE_UPDATES = 1"))
        conn.commit()
        log("Commit OK!")

        # Verify
        result2 = conn.execute(text("SELECT id, role, feature_flags FROM users"))
        for row in result2:
            log(f"After: id={row[0]} role={row[1]} ff={str(row[2])[:100]}")

except Exception as e:
    import traceback
    log("ERROR: " + str(e))
    log(traceback.format_exc())

log("=== Done ===")

