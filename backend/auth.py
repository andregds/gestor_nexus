from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User
import os
from dotenv import load_dotenv

load_dotenv()

# IMPORTANTE: o mesmo default deve existir em core/security.py (que assina o
# token). Sem isso, os.getenv retornaria None e jwt.decode lancaria JWKError,
# gerando HTTP 500 em toda rota autenticada.
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10080))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    plain_password_bytes = _normalize_password_bytes(plain_password)
    hashed_password_bytes = _normalize_password_bytes(hashed_password, allow_empty=True)
    if not hashed_password_bytes:
        return False
    return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)

def get_password_hash(password):
    password_bytes = _normalize_password_bytes(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _normalize_password_bytes(value, allow_empty=False):
    if value is None:
        return b"" if allow_empty else b""
    if isinstance(value, bytes):
        normalized = value
    elif isinstance(value, bytearray):
        normalized = bytes(value)
    elif isinstance(value, str):
        normalized = value.encode("utf-8")
    else:
        normalized = str(value).encode("utf-8")
    return normalized[:72]

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user
