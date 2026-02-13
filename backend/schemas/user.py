# backend/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserSettingsUpdate(BaseModel):
    whatsapp_number: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notify_when_down: Optional[bool] = None
    notify_when_up: Optional[bool] = None
    notify_when_slow: Optional[bool] = None


# --- NOVO SCHEMA PARA BLOQUEIO ---
class BlockUserRequest(BaseModel):
    reason: Optional[str] = None
# ---------------------------------


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    whatsapp_connected: bool
    notifications_enabled: bool
    whatsapp_number: Optional[str] = None
    whatsapp_instance: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notify_when_down: bool
    notify_when_up: bool
    notify_when_slow: bool

    # --- NOVOS CAMPOS NA RESPOSTA DA API ---
    role: str
    permissions: Dict[str, Any]
    client_limit: int
    is_active: bool
    block_reason: Optional[str] = None  # <-- CAMPO ADICIONADO AQUI
    # ---------------------------------------

    class Config:
        from_attributes = True
