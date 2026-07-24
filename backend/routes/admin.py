from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.dependencies import get_current_user, get_db
from models import User
from schemas.user import (
    BlockUserRequest,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_PAYMENT_API_SETTINGS,
    DEFAULT_PERMISSIONS,
    DEFAULT_RESELLER_FEATURE_FLAGS,
    FeatureFlagsUpdate,
    ResellerFeatureFlagsUpdate,
    UserResponse,
)

router = APIRouter(prefix="/admin", tags=["Administração"])


def _safe_dict(value, default):
    return value if isinstance(value, dict) else default.copy()


def get_super_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas Super Administradores podem acessar este recurso.",
        )
    return current_user


def _normalize_user(user: User):
    user.permissions = _safe_dict(user.permissions, DEFAULT_PERMISSIONS)
    user.feature_flags = _safe_dict(user.feature_flags, DEFAULT_FEATURE_FLAGS)
    user.reseller_feature_flags = _safe_dict(
        user.reseller_feature_flags, DEFAULT_RESELLER_FEATURE_FLAGS
    )
    user.payment_api_settings = _safe_dict(
        user.payment_api_settings, DEFAULT_PAYMENT_API_SETTINGS
    )
    effective = DEFAULT_FEATURE_FLAGS.copy()
    effective.update(user.feature_flags)
    if user.role == "super_admin":
        user.feature_flags["admin"] = True
        effective["admin"] = True
    object.__setattr__(user, "effective_feature_flags", effective)
    return user


@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(get_super_admin)])
def list_all_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.name.asc()).all()
    return [_normalize_user(user) for user in users]


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


@router.put("/users/{user_id}/block", dependencies=[Depends(get_super_admin)])
def block_user(user_id: int, payload: BlockUserRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = False
    user.block_reason = payload.reason
    db.commit()
    return {"message": f"Usuário '{user.name}' bloqueado.", "reason": payload.reason}


@router.put("/users/{user_id}/unblock", dependencies=[Depends(get_super_admin)])
def unblock_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = True
    user.block_reason = None
    db.commit()
    return {"message": f"Usuário '{user.name}' desbloqueado."}


@router.delete("/users/{user_id}", dependencies=[Depends(get_super_admin)])
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode deletar a si mesmo.")
    db.delete(user)
    db.commit()
    return {"message": f"Usuário '{user.name}' deletado com sucesso."}


@router.put("/feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_feature_flags(
    user_id: int,
    payload: FeatureFlagsUpdate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    current_flags = _safe_dict(user.feature_flags, DEFAULT_FEATURE_FLAGS)
    for key, value in payload.feature_flags.items():
        if key in DEFAULT_FEATURE_FLAGS and isinstance(value, bool):
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


@router.put("/reseller-feature-flags/{user_id}", dependencies=[Depends(get_super_admin)])
def update_reseller_feature_flags(
    user_id: int,
    payload: ResellerFeatureFlagsUpdate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    current_flags = _safe_dict(user.reseller_feature_flags, DEFAULT_RESELLER_FEATURE_FLAGS)
    for key, value in payload.reseller_feature_flags.items():
        if key in DEFAULT_RESELLER_FEATURE_FLAGS and isinstance(value, bool):
            current_flags[key] = value
    for key, default_value in DEFAULT_RESELLER_FEATURE_FLAGS.items():
        current_flags.setdefault(key, default_value)

    user.reseller_feature_flags = current_flags
    flag_modified(user, "reseller_feature_flags")
    db.commit()
    db.refresh(user)
    return {
        "message": "Padrão de revendedor atualizado",
        "reseller_feature_flags": user.reseller_feature_flags,
    }
