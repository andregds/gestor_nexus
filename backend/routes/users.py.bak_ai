# backend/routes/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

# Imports do projeto
from core.dependencies import get_db, get_current_user
from schemas.user import UserResponse, UserSettingsUpdate
from models import User
from telegram_utils import send_telegram_message

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """Retorna informações do usuário logado."""
    return current_user


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
    return user_in_db


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