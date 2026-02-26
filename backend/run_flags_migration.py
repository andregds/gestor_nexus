#!/usr/bin/env python3
"""
Script de migração para adicionar feature_flags e reseller_feature_flags na tabela users.
Execute: python run_flags_migration.py
"""
import os
import sys
import json

# Garante que consegue importar dotenv
sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql
import re

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://gest_user_nexus_monitor:Hps%4014033@109.199.107.136:3306/gest_nexus_monitor"
)

# Parsear a URL manualmente
# formato: mysql+pymysql://user:pass@host:port/db
m = re.match(r'mysql\+pymysql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)', DATABASE_URL.strip('"\''))
if not m:
    print("ERRO: Não consegui parsear DATABASE_URL:", DATABASE_URL)
    sys.exit(1)

user = m.group(1)
password = m.group(2).replace('%40', '@')
host = m.group(3)
port = int(m.group(4)) if m.group(4) else 3306
database = m.group(5)

print(f"Conectando a MySQL: {user}@{host}:{port}/{database}")

try:
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connect_timeout=15,
        charset='utf8mb4'
    )
    print("✅ Conexão estabelecida!")
except Exception as e:
    print(f"❌ Erro ao conectar: {e}")
    sys.exit(1)

cursor = conn.cursor()

# 1. Adicionar colunas se não existirem
print("\n📋 Adicionando colunas...")
sqls = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
]
for sql in sqls:
    try:
        cursor.execute(sql)
        print(f"  ✅ {sql[:70]}")
    except Exception as e:
        print(f"  ⚠️  {e}")

# 2. Atualizar super_admin com admin=True
print("\n👑 Atualizando super_admin...")
ff_super = json.dumps({
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": True
})
rff_super = json.dumps({
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
})
cursor.execute(
    "UPDATE users SET feature_flags = %s, reseller_feature_flags = %s WHERE role = 'super_admin'",
    (ff_super, rff_super)
)
print(f"  ✅ {cursor.rowcount} usuário(s) super_admin atualizados")

# 3. Atualizar demais usuários onde flags são NULL
print("\n👤 Atualizando demais usuários...")
ff_user = json.dumps({
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
})
cursor.execute(
    "UPDATE users SET feature_flags = %s WHERE feature_flags IS NULL",
    (ff_user,)
)
print(f"  ✅ feature_flags: {cursor.rowcount} usuário(s) atualizados")

cursor.execute(
    "UPDATE users SET reseller_feature_flags = %s WHERE reseller_feature_flags IS NULL",
    (ff_user,)
)
print(f"  ✅ reseller_feature_flags: {cursor.rowcount} usuário(s) atualizados")

conn.commit()

# 4. Verificar resultado
print("\n🔍 Verificando resultado:")
cursor.execute("""
    SELECT id, email, role,
           JSON_EXTRACT(feature_flags, '$.admin') AS flag_admin,
           JSON_EXTRACT(feature_flags, '$.dashboard') AS flag_dashboard
    FROM users
    LIMIT 20
""")
rows = cursor.fetchall()
print(f"  {'ID':<5} {'Email':<30} {'Role':<15} {'admin':<8} {'dash':<8}")
print(f"  {'-'*5} {'-'*30} {'-'*15} {'-'*8} {'-'*8}")
for r in rows:
    print(f"  {r[0]:<5} {str(r[1]):<30} {str(r[2]):<15} {str(r[3]):<8} {str(r[4]):<8}")

cursor.close()
conn.close()
print("\n✅ Migração concluída com sucesso!")

