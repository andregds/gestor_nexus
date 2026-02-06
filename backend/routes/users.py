# backend/routes/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.dependencies import get_db, get_current_user
from schemas.user import UserResponse, UserSettingsUpdate
from models import User
from telegram_utils import send_telegram_message

router = APIRouter(prefix="/users", tags=["Usuários"])

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """Retorna informações do usuário logado."""
    return current_user

# Nova rota para salvar configurações
@router.patch("/me/settings", response_model=UserResponse)
def update_user_settings(
        settings: UserSettingsUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):

    user_in_db = db.merge(current_user)

    # Atualiza número do WhatsApp (se fornecido, ou permite limpar se enviar string vazia)
    if settings.whatsapp_number is not None:
        user_in_db.whatsapp_number = settings.whatsapp_number

    # Atualiza configurações do Telegram (NOVO)
    if settings.telegram_token is not None:
        user_in_db.telegram_token = settings.telegram_token
    if settings.telegram_chat_id is not None:
        user_in_db.telegram_chat_id = settings.telegram_chat_id

    # Atualiza flags de notificação (Verificamos se não é None para permitir atualização parcial)
    if settings.notify_when_down is not None:
        user_in_db.notify_when_down = settings.notify_when_down
    if settings.notify_when_up is not None:
        user_in_db.notify_when_up = settings.notify_when_up
    if settings.notify_when_slow is not None:
        user_in_db.notify_when_slow = settings.notify_when_slow

    db.commit()
    db.refresh(user_in_db)
    return user_in_db


# --- ADICIONE ESTA NOVA ROTA NO FINAL ---
@router.post("/me/telegram/test")
async def test_telegram_notification(
        current_user: User = Depends(get_current_user)
):
    """Envia uma mensagem de teste para o Telegram configurado."""

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