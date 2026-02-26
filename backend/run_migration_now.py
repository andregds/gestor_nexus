hub essa versão com o """
Script direto de migração: adiciona feature_flags e reseller_feature_flags
ao banco MySQL remoto especificado no .env

Execute:
    python run_migration_now.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Lê direto o .env para garantir que DATABASE_URL está carregado
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

DATABASE_URL = os.getenv("DATABASE_URL", "")
print(f"DATABASE_URL: {DATABASE_URL[:60]}...")

import pymysql
from urllib.parse import urlparse, unquote

# Parse da URL mysql+pymysql://user:pass@host:port/db
url = DATABASE_URL.replace("mysql+pymysql://", "").replace("mysql://", "")
# Formato: user:pass@host:port/db
at = url.rfind('@')
userinfo = url[:at]
hostinfo = url[at+1:]

colon = userinfo.find(':')
db_user = unquote(userinfo[:colon])
db_pass = unquote(userinfo[colon+1:])

slash = hostinfo.find('/')
host_port = hostinfo[:slash]
db_name = hostinfo[slash+1:]

if ':' in host_port:
    db_host, db_port = host_port.split(':')
    db_port = int(db_port)
else:
    db_host = host_port
    db_port = 3306

print(f"Conectando em: {db_host}:{db_port} / {db_name} como {db_user}")

DEFAULT_FLAGS = {
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
}
DEFAULT_PERMS = {
    "can_view_dashboard": True, "can_view_clients": True,
    "can_view_integrations": True, "can_view_settings": True,
}

try:
    conn = pymysql.connect(
        host=db_host, port=db_port,
        user=db_user, password=db_pass,
        database=db_name, charset='utf8mb4',
        connect_timeout=15
    )
    cursor = conn.cursor()
    print("✅ Conectado ao MySQL!\n")

    # 1) Verifica e adiciona colunas
    cols_to_add = [
        ("feature_flags", "ALTER TABLE users ADD COLUMN feature_flags JSON DEFAULT NULL"),
        ("reseller_feature_flags", "ALTER TABLE users ADD COLUMN reseller_feature_flags JSON DEFAULT NULL"),
        ("permissions", "ALTER TABLE users ADD COLUMN permissions JSON DEFAULT NULL"),
        ("block_reason", "ALTER TABLE users ADD COLUMN block_reason VARCHAR(255) DEFAULT NULL"),
        ("client_limit", "ALTER TABLE users ADD COLUMN client_limit INT NOT NULL DEFAULT 0"),
    ]

    print("[1/3] Verificando colunas...")
    for col_name, stmt in cols_to_add:
        cursor.execute(f"SHOW COLUMNS FROM users LIKE '{col_name}'")
        exists = cursor.fetchone() is not None
        if not exists:
            print(f"  ➕ Adicionando '{col_name}'...")
            try:
                cursor.execute(stmt)
                conn.commit()
                print(f"  ✔ '{col_name}' adicionada!")
            except Exception as e:
                conn.rollback()
                print(f"  ⚠️  Erro: {e}")
        else:
            print(f"  ✔ '{col_name}' já existe.")

    # 2) Lê usuários
    print("\n[2/3] Lendo usuários...")
    cursor.execute("SELECT id, role, feature_flags, reseller_feature_flags, permissions FROM users")
    rows = cursor.fetchall()
    print(f"  Encontrados {len(rows)} usuário(s).")

    # 3) Atualiza flags nulos
    print("\n[3/3] Atualizando feature_flags e permissions...")
    updated = 0
    for row in rows:
        uid, role = row[0], row[1]
        raw_ff, raw_rff, raw_p = row[2], row[3], row[4]

        def parse_j(v, default):
            if isinstance(v, dict): return v
            try:
                parsed = json.loads(v) if isinstance(v, str) and v.strip() not in ('', 'null') else None
                return parsed if isinstance(parsed, dict) else default.copy()
            except:
                return default.copy()

        ff  = parse_j(raw_ff,  DEFAULT_FLAGS)
        rff = parse_j(raw_rff, DEFAULT_FLAGS)
        p   = parse_j(raw_p,   DEFAULT_PERMS)

        if role == "super_admin":
            ff["admin"] = True

        cursor.execute(
            "UPDATE users SET feature_flags=%s, reseller_feature_flags=%s, permissions=%s WHERE id=%s",
            (json.dumps(ff), json.dumps(rff), json.dumps(p), uid)
        )
        updated += 1

    conn.commit()
    print(f"  ✔ {updated} usuário(s) atualizados!")

    # Verificação final
    print("\n--- Verificação ---")
    cursor.execute("SELECT id, email, role, feature_flags FROM users LIMIT 10")
    for row in cursor.fetchall():
        print(f"  id={row[0]}, email={row[1]}, role={row[2]}, ff={str(row[3])[:60]}")

    cursor.close()
    conn.close()
    print("\n✅ Migração concluída com sucesso!")

except Exception as e:
    print(f"\n❌ Erro: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

