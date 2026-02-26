#!/usr/bin/env python3
"""
Script para executar a migração MySQL do Nexus Monitor.
Execute este script a partir do diretório raiz do projeto:
  python run_migration.py
"""
import sys
import os

# Lê as variáveis do .env do backend
ENV_PATH = os.path.join(os.path.dirname(__file__), 'backend', '.env')
DB_URL = None

if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith('DATABASE_URL'):
                DB_URL = line.split('=', 1)[1].strip().strip('"').strip("'")
                break

if not DB_URL:
    print("❌ DATABASE_URL não encontrada em backend/.env")
    sys.exit(1)

print(f"📦 Conectando ao banco: {DB_URL[:40]}...")

try:
    from sqlalchemy import create_engine, text
    engine = create_engine(DB_URL)
except ImportError:
    print("❌ SQLAlchemy não instalado. Execute: pip install sqlalchemy pymysql")
    sys.exit(1)

SQL_FILE = os.path.join(os.path.dirname(__file__), 'migrate_mysql.sql')
if not os.path.exists(SQL_FILE):
    print(f"❌ Arquivo de migração não encontrado: {SQL_FILE}")
    sys.exit(1)

with open(SQL_FILE, 'r', encoding='utf-8') as f:
    sql_content = f.read()

# Remove comentários de linha e divide em statements
statements = []
current = []
for line in sql_content.splitlines():
    stripped = line.strip()
    if stripped.startswith('--') or stripped.startswith('#'):
        continue
    current.append(line)
    if stripped.endswith(';'):
        stmt = '\n'.join(current).strip()
        if stmt and stmt != ';':
            statements.append(stmt)
        current = []

print(f"📋 {len(statements)} instruções SQL encontradas.")

errors = []
successes = 0

with engine.connect() as conn:
    for i, stmt in enumerate(statements, 1):
        # Pula statements vazios
        if not stmt.replace(';', '').strip():
            continue
        # Remove o ; final pois SQLAlchemy text() não precisa
        clean_stmt = stmt.rstrip(';').strip()
        if not clean_stmt:
            continue
        try:
            conn.execute(text(clean_stmt))
            conn.commit()
            successes += 1
            preview = clean_stmt[:60].replace('\n', ' ')
            print(f"  ✅ [{i:02d}] {preview}...")
        except Exception as e:
            err_msg = str(e)
            # Ignora erros de "Duplicate column" (já existe) e FK já existe
            if any(x in err_msg.lower() for x in [
                'duplicate column', 'already exists', '1060', '1050',
                'can\'t create table', 'errno: 121', '1826'
            ]):
                preview = clean_stmt[:60].replace('\n', ' ')
                print(f"  ⚠️  [{i:02d}] Ignorado (já existe): {preview}...")
                successes += 1
            else:
                preview = clean_stmt[:80].replace('\n', ' ')
                print(f"  ❌ [{i:02d}] ERRO: {err_msg[:120]}")
                print(f"      SQL: {preview}")
                errors.append((i, err_msg))

print()
print("=" * 60)
if errors:
    print(f"⚠️  Migração concluída com {len(errors)} erro(s) e {successes} sucesso(s).")
    print("   Erros críticos acima. Verifique manualmente se necessário.")
else:
    print(f"✅ Migração concluída com sucesso! {successes} instrução(ões) executada(s).")
print("=" * 60)

