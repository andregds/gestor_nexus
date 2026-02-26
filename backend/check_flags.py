import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from database import engine
from models import User
from sqlalchemy.orm import Session

s = Session(engine)
users = s.query(User).all()
for u in users:
    print(f"ID={u.id} role={u.role} feature_flags={u.feature_flags}")
s.close()

