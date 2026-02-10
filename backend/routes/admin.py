# backend/routes/admin.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from core.dependencies import get_db, get_current_user
from models import User
from schemas.user import UserResponse # Reutilizamos a resposta que já tem role e permissions

router = APIRouter(prefix="/admin", tags=["Administração"])

# --- Dependência de Segurança ---
def get_super_admin(current_user: User = Depends(get_current_user)):
    """Verifica se o usuário logado é um super_admin."""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas Super Administradores podem acessar este recurso."
        )
    return current_user

# --- Rotas de Admin ---
@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(get_super_admin)])
def list_all_users(db: Session = Depends(get_db)):
    """
    (Apenas Super Admin) Retorna uma lista de todos os usuários do sistema.
    """
    return db.query(User).all()

# Aqui você adicionaria rotas para criar/editar usuários e suas permissões
# Ex: @router.put("/users/{user_id}/permissions")
