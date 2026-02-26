"""
Script de migração - adiciona feature_flags e reseller_feature_flags na tabela users.
Execute: python migrate_now.py
"""
import sys
import pymysql
import urllib.parse

DATABASE_URL = "mysql+pymysql://gest_user_nexus_monitor:Hps%4014033@109.199.107.136:3306/gest_nexus_monitor"

url = DATABASE_URL.replace("mysql+pymysql://", "")
user_pass, host_db = url.split("@", 1)
user, password = user_pass.split(":", 1)
password = urllib.parse.unquote(password)
host_port, database = host_db.split("/", 1)
if ":" in host_port:
    host, port_str = host_port.split(":", 1)
    port = int(port_str)
else:
    host = host_port
    port = 3306

sys.stdout.write(f"Conectando a {host}:{port}/{database} como {user}...\n")
sys.stdout.flush()

try:
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connect_timeout=30
    )
    sys.stdout.write("Conexao estabelecida!\n")
    sys.stdout.flush()
except Exception as e:
    sys.stdout.write(f"ERRO ao conectar: {e}\n")
    sys.stdout.flush()
    sys.exit(1)

cursor = conn.cursor()

# Adicionar colunas
sqls = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
]
for sql in sqls:
    try:
        cursor.execute(sql)
        sys.stdout.write(f"OK DDL: {sql[:70]}\n")
    except Exception as e:
        sys.stdout.write(f"INFO DDL: {e}\n")
    sys.stdout.flush()

conn.commit()

# Buscar usuários
cursor.execute("SELECT id, role FROM users")
users = cursor.fetchall()
sys.stdout.write(f"Usuarios encontrados: {len(users)}\n")
sys.stdout.flush()

default_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": false}'
super_admin_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": true}'
reseller_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": false}'

updated = 0
for uid, role in users:
    flags = super_admin_flags if role == "super_admin" else default_flags
    try:
        cursor.execute(
            "UPDATE users SET feature_flags = %s, reseller_feature_flags = %s WHERE id = %s",
            (flags, reseller_flags, uid)
        )
        sys.stdout.write(f"  Atualizado id={uid} role={role}\n")
        updated += 1
    except Exception as e:
        sys.stdout.write(f"  ERRO id={uid}: {e}\n")
    sys.stdout.flush()

conn.commit()

# Verificar resultado
cursor.execute("SELECT id, email, role, feature_flags FROM users LIMIT 10")
rows = cursor.fetchall()
sys.stdout.write("\n=== Resultado ===\n")
for row in rows:
    sys.stdout.write(f"id={row[0]} email={row[1]} role={row[2]}\n")
    sys.stdout.write(f"  feature_flags={row[3]}\n")
sys.stdout.flush()

cursor.close()
conn.close()
sys.stdout.write(f"\nMigracao concluida! {updated} usuarios atualizados.\n")
sys.stdout.flush()

