# backend/core/security.py
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações de Segurança
# Em produção, certifique-se de ter SECRET_KEY no seu arquivo .env
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    """Verifica se a senha em texto plano corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """Gera o hash da senha."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um token JWT de acesso."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt