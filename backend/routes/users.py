# backend/routes/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, object_session
from pydantic import BaseModel
from typing import Optional

# Imports do projeto
from core.dependencies import get_db, get_current_user
from schemas.user import UserResponse, UserSettingsUpdate
from models import User

# Defaults para evitar None em permissões/feature flags antigos
DEFAULT_PERMISSIONS = {
    "can_view_dashboard": True,
    "can_view_clients": True,
    "can_view_integrations": True,
    "can_view_settings": True,
}

DEFAULT_FEATURE_FLAGS = {
    "dashboard": True,
    "clients": True,
    "products": True,
    "whatsapp": True,
    "telegram": True,
    "settings": True,
    "resell": True,
    # somente super admin libera o console
    "admin": False,
}
DEFAULT_RESELLER_FEATURE_FLAGS = DEFAULT_FEATURE_FLAGS.copy()


def _safe_dict(value, default):
    return value if isinstance(value, dict) else default.copy()


def _compute_effective_flags(user: User, user_flags: dict, db: Optional[Session]):
    effective = DEFAULT_FEATURE_FLAGS.copy()

    # Herda padrão do dono (quando o dono é revendedor) caso exista
    parent_flags = None
    if user.owner_id and db:
        parent = db.query(User).filter(User.id == user.owner_id).first()
        if parent and isinstance(parent.reseller_feature_flags, dict):
            parent_flags = parent.reseller_feature_flags
    if parent_flags:
        effective.update(parent_flags)

    # Aplica overrides do próprio usuário
    effective.update(user_flags or {})

    # Super admin sempre enxerga o console
    if user.role == "super_admin":
        effective["admin"] = True

    return effective


def _ensure_defaults(user: User, db: Optional[Session] = None):
    """Garante que permissions e feature_flags sejam dicts e gera effective_feature_flags."""
    if not user:
        return user

    # Normaliza todos os campos para dict
    permissions = _safe_dict(user.permissions, DEFAULT_PERMISSIONS)
    user_flags = _safe_dict(user.feature_flags, DEFAULT_FEATURE_FLAGS)
    reseller_flags = _safe_dict(user.reseller_feature_flags, DEFAULT_RESELLER_FEATURE_FLAGS)

    # Super admin não pode perder o console
    if user.role == "super_admin":
        user_flags["admin"] = True

    effective_flags = _compute_effective_flags(user, user_flags, db)

    # Aplica no objeto carregado na sessão atual
    user.permissions = permissions
    user.feature_flags = user_flags
    user.reseller_feature_flags = reseller_flags
    user.effective_feature_flags = effective_flags  # type: ignore[attr-defined]

    # Persiste apenas se tivermos sessão válida e o objeto estiver nela
    if db and object_session(user) is db:
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna informações do usuário logado garantindo dicts nos campos opcionais."""
    # Recarrega o usuário na sessão atual para evitar conflitos entre sessões
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return _ensure_defaults(user_db, db)


# Rota para salvar configurações gerais
@router.patch("/me/settings", response_model=UserResponse)
def update_user_settings(
        settings: UserSettingsUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    # Garante que o usuário está na sessão atual
    user_in_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_in_db:
        # Fallback caso não encontre (raro se estiver logado)
        user_in_db = db.merge(current_user)

    if settings.whatsapp_number is not None:
        user_in_db.whatsapp_number = settings.whatsapp_number

    if settings.telegram_token is not None:
        user_in_db.telegram_token = settings.telegram_token
    if settings.telegram_chat_id is not None:
        user_in_db.telegram_chat_id = settings.telegram_chat_id

    if settings.notify_when_down is not None:
        user_in_db.notify_when_down = settings.notify_when_down
    if settings.notify_when_up is not None:
        user_in_db.notify_when_up = settings.notify_when_up
    if settings.notify_when_slow is not None:
        user_in_db.notify_when_slow = settings.notify_when_slow

    db.commit()
    db.refresh(user_in_db)
    return _ensure_defaults(user_in_db, db)


@router.post("/me/telegram/test")
async def test_telegram_notification(
        current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_token or not current_user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Telegram não configurado. Salve as configurações primeiro.")

    try:
        await send_telegram_message(
            token=current_user.telegram_token,
            chat_id=current_user.telegram_chat_id,
            message="🔔 *Teste de Notificação - Nexus Monitor*\n\nSe você recebeu esta mensagem, a integração está funcionando perfeitamente! 🚀"
        )
        return {"message": "Mensagem de teste enviada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ROTAS DE AGENDAMENTO (CORRIGIDAS)
# ==========================================

class ScheduleUpdate(BaseModel):
    time: str  # Formato "HH:MM"
    enabled: bool = True  # Campo essencial para o switch funcionar


@router.put("/me/schedule")
def update_notification_schedule(
        schedule_data: ScheduleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Atualiza o horário e se o agendamento está ativo."""

    # --- CORREÇÃO PRINCIPAL AQUI ---
    # Buscamos o usuário novamente na sessão atual para garantir que o commit funcione
    user_db = db.query(User).filter(User.id == current_user.id).first()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Atualiza os campos
    user_db.notification_time = schedule_data.time
    user_db.notifications_enabled = schedule_data.enabled

    db.commit()
    db.refresh(user_db)

    return {
        "message": "Configuração de agendamento atualizada com sucesso!",
        "time": user_db.notification_time,
        "enabled": user_db.notifications_enabled
    }


@router.get("/me/schedule")
def get_notification_schedule(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)  # Adicionado DB session para leitura atualizada
):
    """Retorna o horário e status configurados."""
    # Também garantimos a leitura atualizada do banco
    user_db = db.query(User).filter(User.id == current_user.id).first()

    return {
        "time": user_db.notification_time or "09:00",
        "enabled": user_db.notifications_enabled if user_db.notifications_enabled is not None else True
    }