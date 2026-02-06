# backend/core/dependencies.py
from sqlalchemy.orm import Session
from database import SessionLocal
from auth import get_current_user # Assumindo que auth.py contém get_current_user

# Dependency para obter a sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
