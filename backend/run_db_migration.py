"""
Script para adicionar colunas feature_flags e reseller_feature_flags na tabela users do MySQL.
Execute: python run_db_migration.py
"""
import pymysql
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip('"').strip("'")

print(f"DATABASE_URL encontrado: {DATABASE_URL[:40]}...")

# Parse manual da URL
# formato: mysql+pymysql://user:pass@host:port/db
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

print(f"Conectando a {host}:{port}/{database} como {user}...")

conn = pymysql.connect(
    host=host,
    port=port,
    user=user,
    password=password,
    database=database,
    connect_timeout=30
)
print("Conexão estabelecida com sucesso!")
cursor = conn.cursor()

# Passo 1: Adicionar colunas se não existirem
add_columns_sqls = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
]

for sql in add_columns_sqls:
    try:
        cursor.execute(sql)
        print(f"OK (DDL): {sql[:80].strip()}")
    except Exception as e:
        print(f"INFO (DDL): {e}")

conn.commit()

# Passo 2: Buscar todos os IDs para fazer UPDATE seguro por PK
cursor.execute("SELECT id, role FROM users")
users = cursor.fetchall()
print(f"\nEncontrados {len(users)} usuários para migrar.")

default_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": false}'
super_admin_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": true}'
reseller_flags = '{"dashboard": true, "clients": true, "products": true, "whatsapp": true, "telegram": true, "settings": true, "resell": true, "admin": false}'

updated = 0
for user_id, role in users:
    flags = super_admin_flags if role == 'super_admin' else default_flags
    try:
        cursor.execute(
            "UPDATE users SET feature_flags = %s, reseller_feature_flags = %s WHERE id = %s",
            (flags, reseller_flags, user_id)
        )
        updated += 1
        print(f"  Atualizado: id={user_id} role={role}")
    except Exception as e:
        print(f"  ERRO id={user_id}: {e}")

conn.commit()
print(f"\n{updated} usuários atualizados com feature_flags.")

# Verifica resultado
cursor.execute("SELECT id, email, role, feature_flags, reseller_feature_flags FROM users LIMIT 10")
rows = cursor.fetchall()
print("\n=== Resultado da migração ===")
for row in rows:
    print(f"id={row[0]} email={row[1]} role={row[2]}")
    print(f"  feature_flags={row[3]}")
    print(f"  reseller_ff={row[4]}")

cursor.close()
conn.close()
print("\nMigração concluída com sucesso!")
