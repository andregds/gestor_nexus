# backend/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

# Ajuste: Importando de core.dependencies
from core.dependencies import get_db
# Ajuste: Importando de core.security (onde as funções de hash/token devem estar)
from core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from schemas.auth import Token
from schemas.user import UserCreate, UserResponse
from models import User

# CORREÇÃO: Removido prefix="/auth" para que as rotas sejam /register e /token
# Isso corrige o erro 404 pois o frontend chama http://localhost:8000/token
router = APIRouter(tags=["Autenticação"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registra um novo usuário."""
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "E-mail já cadastrado.")

    hashed_password = get_password_hash(user.password)
    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password,
        notifications_enabled=True # Garante que o usuário inicie com notificações ativas
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Realiza login e retorna o token de acesso (JWT)."""
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}