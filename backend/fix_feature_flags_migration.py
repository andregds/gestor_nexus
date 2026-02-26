"""
Script de migração: adiciona as colunas feature_flags e reseller_feature_flags
na tabela users e popula com valores padrão.

Execute a partir da pasta backend:
    python fix_feature_flags_migration.py
"""
import sys
import os
import json

# Garante que o diretório backend esteja no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine
from sqlalchemy import text

DEFAULT_FLAGS = {
    "dashboard": True, "clients": True, "products": True,
    "whatsapp": True, "telegram": True, "settings": True,
    "resell": True, "admin": False
}
SUPER_FLAGS = {**DEFAULT_FLAGS, "admin": True}
DEFAULT_PERMS = {
    "can_view_dashboard": True, "can_view_clients": True,
    "can_view_integrations": True, "can_view_settings": True,
}

def run():
    print("=" * 60)
    print("Iniciando migração de feature_flags...")
    print("=" * 60)

    db_url = str(engine.url)
    is_mysql = "mysql" in db_url
    print(f"Banco de dados: {'MySQL' if is_mysql else 'SQLite'}")
    print(f"URL: {db_url[:50]}...")

    try:
        with engine.connect() as conn:
            print("\n[1/4] Verificando/adicionando colunas...")

            if is_mysql:
                cols_to_add = [
                    ("feature_flags", "ALTER TABLE users ADD COLUMN feature_flags JSON DEFAULT NULL"),
                    ("reseller_feature_flags", "ALTER TABLE users ADD COLUMN reseller_feature_flags JSON DEFAULT NULL"),
                    ("permissions", "ALTER TABLE users ADD COLUMN permissions JSON DEFAULT NULL"),
                    ("block_reason", "ALTER TABLE users ADD COLUMN block_reason VARCHAR(255) DEFAULT NULL"),
                    ("client_limit", "ALTER TABLE users ADD COLUMN client_limit INT NOT NULL DEFAULT 0"),
                ]
                for col_name, stmt in cols_to_add:
                    result = conn.execute(text(f"SHOW COLUMNS FROM users LIKE '{col_name}'"))
                    exists = result.fetchone() is not None
                    if not exists:
                        print(f"  ➕ Adicionando coluna '{col_name}'...")
                        try:
                            conn.execute(text(stmt))
                            conn.commit()
                            print(f"  ✔ '{col_name}' adicionada.")
                        except Exception as e:
                            conn.rollback()
                            print(f"  ⚠️  Erro ao adicionar '{col_name}': {e}")
                    else:
                        print(f"  ✔ '{col_name}' já existe.")
            else:
                existing = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
                sqlite_cols = {
                    "feature_flags": "ALTER TABLE users ADD COLUMN feature_flags TEXT DEFAULT NULL",
                    "reseller_feature_flags": "ALTER TABLE users ADD COLUMN reseller_feature_flags TEXT DEFAULT NULL",
                    "permissions": "ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT NULL",
                }
                for col, sql in sqlite_cols.items():
                    if col not in existing:
                        conn.execute(text(sql))
                        conn.commit()
                        print(f"  ✔ '{col}' adicionada (SQLite).")
                    else:
                        print(f"  ✔ '{col}' já existe (SQLite).")

            print("\n[2/4] Lendo usuários existentes...")
            try:
                rows = conn.execute(text(
                    "SELECT id, role, feature_flags, reseller_feature_flags, permissions FROM users"
                )).fetchall()
                print(f"  Encontrados {len(rows)} usuário(s).")
            except Exception as e:
                print(f"  ❌ Erro ao ler usuários: {e}")
                return

            print("\n[3/4] Atualizando registros com NULL...")
            updated = 0
            for row in rows:
                uid, role = row[0], row[1]
                raw_ff, raw_rff, raw_p = row[2], row[3], row[4]

                def parse_json(v, default):
                    if isinstance(v, dict): return v
                    try:
                        parsed = json.loads(v) if isinstance(v, str) and v.strip() not in ('', 'null') else None
                        return parsed if isinstance(parsed, dict) else default.copy()
                    except:
                        return default.copy()

                ff  = parse_json(raw_ff,  DEFAULT_FLAGS)
                rff = parse_json(raw_rff, DEFAULT_FLAGS)
                p   = parse_json(raw_p,   DEFAULT_PERMS)

                if role == "super_admin":
                    ff["admin"] = True

                try:
                    conn.execute(
                        text("UPDATE users SET feature_flags=:ff, reseller_feature_flags=:rff, permissions=:p WHERE id=:id"),
                        {"ff": json.dumps(ff), "rff": json.dumps(rff), "p": json.dumps(p), "id": uid}
                    )
                    updated += 1
                except Exception as e:
                    print(f"  ⚠️  Erro ao atualizar usuário id={uid}: {e}")

            conn.commit()
            print(f"  ✔ {updated} usuário(s) atualizados.")

            print("\n[4/4] Verificação final...")
            result = conn.execute(text(
                "SELECT id, email, role, feature_flags, reseller_feature_flags FROM users LIMIT 10"
            ))
            rows_check = result.fetchall()
            for row in rows_check:
                print(f"  id={row[0]}, email={row[1]}, role={row[2]}")
                print(f"    feature_flags={row[3]}")

            print("\n" + "=" * 60)
            print("✅ Migração concluída com sucesso!")
            print("=" * 60)

    except Exception as e:
        print(f"\n❌ Erro crítico na migração: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
