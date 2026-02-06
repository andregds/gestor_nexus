# backend/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


# CORREÇÃO: Todos os campos agora são Optional com valor padrão None.
# Isso permite enviar apenas os dados do Telegram sem precisar enviar as flags de notificação junto.
class UserSettingsUpdate(BaseModel):
    whatsapp_number: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    notify_when_down: Optional[bool] = None
    notify_when_up: Optional[bool] = None
    notify_when_slow: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    whatsapp_connected: bool
    notifications_enabled: bool
    whatsapp_number: Optional[str] = None
    whatsapp_instance: Optional[str] = None

    # Adicionamos os campos do Telegram na resposta para o frontend carregar os dados salvos
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    notify_when_down: bool
    notify_when_up: bool
    notify_when_slow: bool

    class Config:
        from_attributes = True