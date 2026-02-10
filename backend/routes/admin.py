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

# --- NOVA ROTA: Promover Usuário ---
@router.put("/users/{user_id}/promote-to-super-admin", dependencies=[Depends(get_super_admin)])
def promote_user_to_super_admin(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    (Apenas Super Admin) Promove um usuário específico para o nível de 'super_admin'.
    """
    # Busca o usuário que será promovido
    user_to_promote = db.query(User).filter(User.id == user_id).first()

    if not user_to_promote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {user_id} não encontrado."
        )

    if user_to_promote.role == "super_admin":
        return {"message": f"O usuário '{user_to_promote.name}' já é um super administrador."}

    # Altera a role e salva no banco
    user_to_promote.role = "super_admin"
    db.commit()
    db.refresh(user_to_promote)

    return {"message": f"Usuário '{user_to_promote.name}' promovido a super administrador com sucesso!"}