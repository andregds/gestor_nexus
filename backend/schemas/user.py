# backend/schemas/user.py
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Dict, Any

# Fallbacks used when legacy rows have NULL/invalid JSON
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
    # console de super admin permanece desativado para contas comuns
    "admin": False,
}
DEFAULT_RESELLER_FEATURE_FLAGS = DEFAULT_FEATURE_FLAGS.copy()


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class FeatureFlagsUpdate(BaseModel):
    feature_flags: Dict[str, bool]


class ResellerFeatureFlagsUpdate(BaseModel):
    reseller_feature_flags: Dict[str, bool]


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
    permissions: Dict[str, Any] = Field(default_factory=dict)
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    reseller_feature_flags: Dict[str, bool] = Field(default_factory=dict)
    effective_feature_flags: Dict[str, bool] = Field(default_factory=dict)
    client_limit: int
    is_active: bool
    block_reason: Optional[str] = None  # <-- CAMPO ADICIONADO AQUI
    # ---------------------------------------

    @field_validator("permissions", mode="before")
    def _ensure_permissions(cls, v):
        return v if isinstance(v, dict) else DEFAULT_PERMISSIONS.copy()

    @field_validator("feature_flags", mode="before")
    def _ensure_feature_flags(cls, v):
        return v if isinstance(v, dict) else DEFAULT_FEATURE_FLAGS.copy()

    @field_validator("reseller_feature_flags", mode="before")
    def _ensure_reseller_feature_flags(cls, v):
        return v if isinstance(v, dict) else DEFAULT_RESELLER_FEATURE_FLAGS.copy()

    @field_validator("effective_feature_flags", mode="before")
    def _ensure_effective(cls, v):
        return v if isinstance(v, dict) else DEFAULT_FEATURE_FLAGS.copy()

    class Config:
        from_attributes = True
