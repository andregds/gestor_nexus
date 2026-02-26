"""
apply_migration.py - Execute para adicionar colunas feature_flags ao MySQL
Uso: cd backend && python apply_migration.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from database import engine
DEFAULT_FLAGS = {"dashboard":True,"clients":True,"products":True,"whatsapp":True,"telegram":True,"settings":True,"resell":True,"admin":False}
DEFAULT_PERMS = {"can_view_dashboard":True,"can_view_clients":True,"can_view_integrations":True,"can_view_settings":True}
db_url = str(engine.url)
is_mysql = "mysql" in db_url
print(f"[INFO] Banco: {db_url[:70]}...")
with engine.connect() as conn:
    if is_mysql:
        stmts = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSON DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS client_limit INT NOT NULL DEFAULT 0",
        ]
        for s in stmts:
            try:
                conn.execute(text(s)); conn.commit()
                print(f"[OK] {s[:70]}")
            except Exception as e:
                conn.rollback()
                if "1060" in str(e) or "Duplicate" in str(e):
                    print(f"[SKIP] Coluna ja existe")
                else:
                    print(f"[ERRO] {e}")
    else:
        existing = {r[1] for r in conn.execute(text("PRAGMA table_info(users)"))}
        for col, sql in {
            "feature_flags":"ALTER TABLE users ADD COLUMN feature_flags TEXT DEFAULT NULL",
            "reseller_feature_flags":"ALTER TABLE users ADD COLUMN reseller_feature_flags TEXT DEFAULT NULL",
            "permissions":"ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT NULL",
        }.items():
            if col not in existing:
                conn.execute(text(sql)); conn.commit(); print(f"[OK] {col}")
            else:
                print(f"[SKIP] {col}")
    rows = conn.execute(text("SELECT id, role, feature_flags, reseller_feature_flags, permissions FROM users")).fetchall()
    updated = 0
    for row in rows:
        uid, role = row[0], row[1]
        def _p(v, d):
            if isinstance(v, dict): return v
            try: return json.loads(v) if isinstance(v, str) and v.strip() not in ('','null') else None
            except: return None
        ff = _p(row[2], DEFAULT_FLAGS) or DEFAULT_FLAGS.copy()
        rff = _p(row[3], DEFAULT_FLAGS) or DEFAULT_FLAGS.copy()
        p = _p(row[4], DEFAULT_PERMS) or DEFAULT_PERMS.copy()
        if role == "super_admin":
            ff["admin"] = True; rff["admin"] = True
        conn.execute(text("UPDATE users SET feature_flags=:ff, reseller_feature_flags=:rff, permissions=:p WHERE id=:id"),
            {"ff":json.dumps(ff),"rff":json.dumps(rff),"p":json.dumps(p),"id":uid})
        updated += 1
    conn.commit()
    print(f"[OK] {updated} usuario(s) atualizados.")
print("Migracao concluida!")
