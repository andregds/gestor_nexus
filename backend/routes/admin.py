# backend/routes/admin.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List, Optional
from pydantic import BaseModel

from core.dependencies import get_db, get_current_user
from models import User
from schemas.user import UserResponse, FeatureFlagsUpdate, DEFAULT_FEATURE_FLAGS, ResellerFeatureFlagsUpdate, DEFAULT_RESELLER_FEATURE_FLAGS, BlockUserRequest

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
    """(Apenas Super Admin) Retorna todos os usuários."""
    users = db.query(User).all()
    # Garante que feature_flags não seja None para serialização
    import json
    _DEFAULT = {"dashboard":True,"clients":True,"products":True,"whatsapp":True,
                "telegram":True,"settings":True,"resell":True,"admin":False}
    for u in users:
        if not isinstance(u.feature_flags, dict):
            u.feature_flags = _DEFAULT.copy()
        if not isinstance(u.reseller_feature_flags, dict):
            u.reseller_feature_flags = _DEFAULT.copy()
        if not isinstance(u.permissions, dict):
            u.permissions = {"can_view_dashboard":True,"can_view_clients":True,
                             "can_view_integrations":True,"can_view_settings":True}
        if u.role == "super_admin":
            u.feature_flags["admin"] = True
    return users

# --- ROTA: Promover Usuário ---
@router.put("/users/{user_id}/promote-to-super-admin", dependencies=[Depends(get_super_admin)])
def promote_user_to_super_admin(user_id: int, db: Session = Depends(get_db)):
    user_to_promote = db.query(User).filter(User.id == user_id).first()
    if not user_to_promote:
        raise HTTPException(status_code=404, detail=f"Usuário com ID {user_id} não encontrado.")
    if user_to_promote.role == "super_admin":
        return {"message": f"O usuário '{user_to_promote.name}' já é um super administrador."}
    user_to_promote.role = "super_admin"
    db.commit()
    db.refresh(user_to_promote)
    return {"message": f"Usuário '{user_to_promote.name}' promovido a super administrador com sucesso!"}

# --- ROTA: Bloquear Usuário ---
@router.put("/users/{user_id}/block", dependencies=[Depends(get_super_admin)])
def block_user(user_id: int, payload: BlockUserRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = False
    user.block_reason = payload.reason
    db.commit()
    return {"message": f"Usuário '{user.name}' bloqueado.", "reason": payload.reason}

# --- ROTA: Desbloquear Usuário ---
@router.put("/users/{user_id}/unblock", dependencies=[Depends(get_super_admin)])
def unblock_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = True
    user.block_reason = None
    db.commit()
    return {"message": f"Usuário '{user.name}' desbloqueado."}

# --- ROTA: Deletar Usuário ---
@router.delete("/users/{user_id}", dependencies=[Depends(get_super_admin)])
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode deletar a si mesmo.")
    db.delete(user)
    db.commit()
    return {"message": f"Usuário '{user.name}' deletado com sucesso."}

# --- ROTA: Atualizar Feature Flags ---
@router.put("/feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_feature_flags(user_id: int, payload: FeatureFlagsUpdate, db: Session = Depends(get_db)):
    """Atualiza os feature flags (menus/páginas visíveis) de um usuário específico."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    current_flags = dict(user.feature_flags) if isinstance(user.feature_flags, dict) else {}
    for key, value in payload.feature_flags.items():
        if key not in DEFAULT_FEATURE_FLAGS:
            continue
        if isinstance(value, bool):
            current_flags[key] = value
    for key, default_value in DEFAULT_FEATURE_FLAGS.items():
        current_flags.setdefault(key, default_value)
    if user.role == "super_admin":
        current_flags["admin"] = True
    user.feature_flags = current_flags
    flag_modified(user, "feature_flags")
    db.commit()
    db.refresh(user)
    return {"message": "Feature flags atualizados", "feature_flags": user.feature_flags}

# --- ROTA: Atualizar Reseller Feature Flags ---
@router.put("/reseller-feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_reseller_feature_flags(user_id: int, payload: ResellerFeatureFlagsUpdate, db: Session = Depends(get_db)):
    """Define o padrão de flags herdado pelos filhos de um revendedor."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    current_flags = dict(user.reseller_feature_flags) if isinstance(user.reseller_feature_flags, dict) else {}
    for key, value in payload.reseller_feature_flags.items():
        if key not in DEFAULT_RESELLER_FEATURE_FLAGS:
            continue
        if isinstance(value, bool):
            current_flags[key] = value
    for key, default_value in DEFAULT_RESELLER_FEATURE_FLAGS.items():
        current_flags.setdefault(key, default_value)
    user.reseller_feature_flags = current_flags
    flag_modified(user, "reseller_feature_flags")
    db.commit()
    db.refresh(user)
    return {"message": "Padrão de revendedor atualizado", "reseller_feature_flags": user.reseller_feature_flags}
