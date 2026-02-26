"""
Script simples para adicionar feature_flags e reseller_feature_flags ao banco MySQL.
"""
import sys, os, json
import pymysql

# Conexão direta
HOST = "109.199.107.136"
PORT = 3306
USER = "gest_user_nexus_monitor"
PASS = "Hps@14033"
DB   = "gest_nexus_monitor"

DEFAULT_FLAGS = {
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
}
DEFAULT_PERMS = {
    "can_view_dashboard": True, "can_view_clients": True,
    "can_view_integrations": True, "can_view_settings": True,
}

print(f"Conectando em {HOST}:{PORT}/{DB}...")
try:
    conn = pymysql.connect(
        host=HOST, port=PORT, user=USER, password=PASS,
        database=DB, charset='utf8mb4', connect_timeout=30
    )
    cur = conn.cursor()
    print("✅ Conectado!\n")

    # Verificar e adicionar colunas
    for col, ddl in [
        ("feature_flags",           "ALTER TABLE users ADD COLUMN feature_flags JSON DEFAULT NULL"),
        ("reseller_feature_flags",  "ALTER TABLE users ADD COLUMN reseller_feature_flags JSON DEFAULT NULL"),
    ]:
        cur.execute(f"SHOW COLUMNS FROM users LIKE '{col}'")
        if not cur.fetchone():
            print(f"  ➕ Adicionando '{col}'...")
            cur.execute(ddl)
            conn.commit()
            print(f"  ✔ '{col}' adicionada!")
        else:
            print(f"  ✔ '{col}' já existe.")

    # Buscar usuários
    cur.execute("SELECT id, role, feature_flags, reseller_feature_flags, permissions FROM users")
    rows = cur.fetchall()
    print(f"\nAtualizando {len(rows)} usuário(s)...")

    def parse_j(v, default):
        if isinstance(v, dict):
            return v
        try:
            parsed = json.loads(v) if isinstance(v, str) and v.strip() not in ('', 'null') else None
            return parsed if isinstance(parsed, dict) else default.copy()
        except:
            return default.copy()

    for row in rows:
        uid, role = row[0], row[1]
        ff  = parse_j(row[2], DEFAULT_FLAGS)
        rff = parse_j(row[3], DEFAULT_FLAGS)
        p   = parse_j(row[4], DEFAULT_PERMS) if row[4] is not None else DEFAULT_PERMS.copy()

        if role == "super_admin":
            ff["admin"] = True

        cur.execute(
            "UPDATE users SET feature_flags=%s, reseller_feature_flags=%s, permissions=%s WHERE id=%s",
            (json.dumps(ff), json.dumps(rff), json.dumps(p), uid)
        )

    conn.commit()
    print("✔ feature_flags populadas!\n")

    # Verificação final
    cur.execute("SELECT id, email, role, feature_flags FROM users LIMIT 10")
    for row in cur.fetchall():
        print(f"  id={row[0]}, email={row[1]}, role={row[2]}, flags={str(row[3])[:80]}")

    cur.close()
    conn.close()
    print("\n✅ Migração concluída com sucesso!")

except Exception as e:
    print(f"\n❌ Erro: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

