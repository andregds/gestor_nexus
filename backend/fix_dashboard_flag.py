#!/usr/bin/env python3
"""Fix dashboard=True for all users."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Fix dashboard=True for super_admin (was set to false)
    result = conn.execute(text(
        "UPDATE users SET feature_flags = JSON_SET(COALESCE(feature_flags, '{}'), '$.dashboard', true) "
        "WHERE JSON_EXTRACT(feature_flags, '$.dashboard') = false OR feature_flags IS NULL"
    ))
    conn.commit()
    print(f"Updated {result.rowcount} rows - dashboard flag fixed.")

    # Check all users
    rows = conn.execute(text("SELECT id, email, role, feature_flags FROM users")).fetchall()
    for row in rows:
        print(f"ID={row[0]}, email={row[1]}, role={row[2]}, flags={row[3]}")

