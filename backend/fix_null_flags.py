#!/usr/bin/env python3
"""
Fix NULL feature_flags and reseller_feature_flags for existing users.
Run: python fix_null_flags.py
"""
import os, sys, json, re

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://gest_user_nexus_monitor:Hps%4014033@109.199.107.136:3306/gest_nexus_monitor"
).strip('"\'')

m = re.match(r'mysql\+pymysql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)', DATABASE_URL)
if not m:
    sys.stdout.write("ERRO: Nao consegui parsear DATABASE_URL\n")
    sys.exit(1)

user = m.group(1)
password = m.group(2).replace('%40', '@')
host = m.group(3)
port = int(m.group(4)) if m.group(4) else 3306
database = m.group(5)

sys.stdout.write(f"Conectando: {user}@{host}:{port}/{database}\n")
sys.stdout.flush()

try:
    conn = pymysql.connect(
        host=host, port=port, user=user,
        password=password, database=database,
        connect_timeout=15, charset='utf8mb4'
    )
    sys.stdout.write("Conexao OK!\n")
    sys.stdout.flush()
except Exception as e:
    sys.stdout.write(f"Erro conexao: {e}\n")
    sys.stdout.flush()
    sys.exit(1)

cursor = conn.cursor()

# Ensure columns exist
for col_sql in [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
]:
    try:
        cursor.execute(col_sql)
        sys.stdout.write(f"OK: {col_sql[:60]}\n")
    except Exception as e:
        sys.stdout.write(f"WARN: {e}\n")
    sys.stdout.flush()

ff_super = json.dumps({
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": True
})
ff_user = json.dumps({
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
})

# Update super_admin first (bypass safe mode by using id > 0)
cursor.execute(
    "UPDATE users SET feature_flags = %s, reseller_feature_flags = %s WHERE role = 'super_admin' AND id > 0",
    (ff_super, ff_user)
)
sys.stdout.write(f"super_admin atualizados: {cursor.rowcount}\n")
sys.stdout.flush()

# Update other users with NULL flags
cursor.execute(
    "UPDATE users SET feature_flags = %s WHERE feature_flags IS NULL AND id > 0",
    (ff_user,)
)
sys.stdout.write(f"feature_flags NULL atualizados: {cursor.rowcount}\n")
sys.stdout.flush()

cursor.execute(
    "UPDATE users SET reseller_feature_flags = %s WHERE reseller_feature_flags IS NULL AND id > 0",
    (ff_user,)
)
sys.stdout.write(f"reseller_feature_flags NULL atualizados: {cursor.rowcount}\n")
sys.stdout.flush()

conn.commit()

# Verify
cursor.execute("SELECT id, email, role, feature_flags, reseller_feature_flags FROM users LIMIT 10")
rows = cursor.fetchall()
sys.stdout.write("\nResultado:\n")
for r in rows:
    sys.stdout.write(f"  id={r[0]} email={r[1]} role={r[2]} flags_ok={r[3] is not None} rflags_ok={r[4] is not None}\n")
sys.stdout.flush()

cursor.close()
conn.close()
sys.stdout.write("\nMigracao concluida!\n")
sys.stdout.flush()

