# backend/routes/admin.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from core.dependencies import get_db, get_current_user
from models import User
from schemas.user import UserResponse, FeatureFlagsUpdate, DEFAULT_FEATURE_FLAGS, ResellerFeatureFlagsUpdate, DEFAULT_RESELLER_FEATURE_FLAGS

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

@router.put("/feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_feature_flags(user_id: int, payload: FeatureFlagsUpdate, db: Session = Depends(get_db)):
    """Atualiza os feature flags (menus/páginas visíveis) de um usuário específico."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    current_flags = user.feature_flags or {}

    # Aceita apenas chaves conhecidas e valores booleanos
    for key, value in payload.feature_flags.items():
        if key not in DEFAULT_FEATURE_FLAGS:
            continue
        if isinstance(value, bool):
            current_flags[key] = value

    # Completa com defaults para evitar None e não aplicar restrição quando ausente
    for key, default_value in DEFAULT_FEATURE_FLAGS.items():
        current_flags.setdefault(key, default_value)

    # Super admin nunca perde acesso ao console
    if user.role == "super_admin":
        current_flags["admin"] = True

    user.feature_flags = current_flags

    db.commit()
    db.refresh(user)
    return {"message": "Feature flags atualizados", "feature_flags": user.feature_flags}

@router.put("/reseller-feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_reseller_feature_flags(user_id: int, payload: ResellerFeatureFlagsUpdate, db: Session = Depends(get_db)):
    """Define o padrão de flags herdado pelos filhos de um revendedor (apenas super_admin pode alterar)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    current_flags = user.reseller_feature_flags or {}

    for key, value in payload.reseller_feature_flags.items():
        if key not in DEFAULT_RESELLER_FEATURE_FLAGS:
            continue
        if isinstance(value, bool):
            current_flags[key] = value

    for key, default_value in DEFAULT_RESELLER_FEATURE_FLAGS.items():
        current_flags.setdefault(key, default_value)

    user.reseller_feature_flags = current_flags

    db.commit()
    db.refresh(user)
    return {"message": "Padrão de revendedor atualizado", "reseller_feature_flags": user.reseller_feature_flags}
