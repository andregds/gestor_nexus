"""
Script de migração: Popula feature_flags e reseller_feature_flags para usuários com NULL.
Execute dentro da pasta backend com o venv ativo:
    python fix_feature_flags.py

Este script:
 1. Garante que as colunas existem na tabela users
 2. Popula valores NULL com os defaults
 3. Garante que super_admin tem admin=True
"""
import sys
import os
import json

# Garante que o diretório do backend está no path
sys.path.insert(0, os.path.dirname(__file__))

from database import engine, SessionLocal
from sqlalchemy import text

DEFAULT_FEATURE_FLAGS = {
    "dashboard": True,
    "clients": True,
    "products": True,
    "whatsapp": True,
    "telegram": True,
    "settings": True,
    "resell": True,
    "admin": False,
}

DEFAULT_RESELLER_FEATURE_FLAGS = DEFAULT_FEATURE_FLAGS.copy()

DEFAULT_PERMISSIONS = {
    "can_view_dashboard": True,
    "can_view_clients": True,
    "can_view_integrations": True,
    "can_view_settings": True,
}


def run():
    db = SessionLocal()
    try:
        # Garante que as colunas existem (MySQL)
        db_url = str(engine.url)
        is_mysql = "mysql" in db_url

        if is_mysql:
            print("🔧 Verificando/criando colunas no MySQL...")
            alter_stmts = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSON DEFAULT NULL",
            ]
            for stmt in alter_stmts:
                try:
                    db.execute(text(stmt))
                    db.commit()
                    print(f"  ✅ {stmt[:70]}...")
                except Exception as e:
                    db.rollback()
                    print(f"  ⚠️  Aviso (esperado se já existe): {e}")

        # Busca todos os usuários
        result = db.execute(text("SELECT id, role, feature_flags, reseller_feature_flags, permissions FROM users"))
        rows = result.fetchall()
        print(f"\n👥 Encontrados {len(rows)} usuário(s). Verificando flags...")

        updated = 0
        for row in rows:
            uid, role = row[0], row[1]
            raw_ff  = row[2]
            raw_rff = row[3]
            raw_p   = row[4]

            # Parseia se for string
            def parse_json(val, default):
                if val is None:
                    return None
                if isinstance(val, dict):
                    return val
                try:
                    parsed = json.loads(val) if isinstance(val, str) else val
                    return parsed if isinstance(parsed, dict) else None
                except Exception:
                    return None

            ff  = parse_json(raw_ff,  DEFAULT_FEATURE_FLAGS)
            rff = parse_json(raw_rff, DEFAULT_RESELLER_FEATURE_FLAGS)
            p   = parse_json(raw_p,   DEFAULT_PERMISSIONS)

            needs_update = False

            if ff is None:
                ff = DEFAULT_FEATURE_FLAGS.copy()
                needs_update = True

            if rff is None:
                rff = DEFAULT_RESELLER_FEATURE_FLAGS.copy()
                needs_update = True

            if p is None:
                p = DEFAULT_PERMISSIONS.copy()
                needs_update = True

            # Super admin sempre tem admin=True
            if role == "super_admin" and not ff.get("admin", False):
                ff["admin"] = True
                needs_update = True

            if needs_update:
                db.execute(
                    text("UPDATE users SET feature_flags = :ff, reseller_feature_flags = :rff, permissions = :p WHERE id = :id"),
                    {
                        "ff":  json.dumps(ff),
                        "rff": json.dumps(rff),
                        "p":   json.dumps(p),
                        "id":  uid,
                    }
                )
                updated += 1
                print(f"  ↻ Usuário ID={uid} role={role} atualizado.")
            else:
                print(f"  ✓ Usuário ID={uid} role={role} já possui flags.")

        db.commit()
        print(f"\n✅ Concluído. {updated} usuário(s) atualizado(s).")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()

