# backend/schemas/user.py
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional, Dict, Any, List

from reminder_utils import (
    DEFAULT_REMINDER_TEMPLATES,
    EMPTY_REMINDER_MEDIA,
    normalize_custom_reminder_scenarios,
    normalize_reminder_media,
    normalize_reminder_templates,
)

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
DEFAULT_PAYMENT_API_SETTINGS = {
    "gateway_name": "InfinitePay Checkout",
    "bank_name": "",
    "handle": "blue-play",
    "api_base_url": "https://api.checkout.infinitepay.io",
    "links_endpoint": "/links",
    "payment_check_endpoint": "/payment_check",
    "webhook_url": "",
    "redirect_url": "",
    "api_key": "",
    "webhook_secret": "",
    "environment": "production",
    "enabled": False,
}


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
    payment_api_settings: Optional[Dict[str, Any]] = None
    reminder_templates: Optional[Dict[str, Any]] = None
    reminder_scenarios: Optional[List[Dict[str, Any]]] = None
    reminder_media: Optional[Dict[str, Any]] = None


# --- NOVO SCHEMA PARA BLOQUEIO ---
class BlockUserRequest(BaseModel):
    reason: Optional[str] = None
# ---------------------------------


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    whatsapp_connected: bool
    notifications_enabled: bool = True
    whatsapp_number: Optional[str] = None
    whatsapp_instance: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notify_when_down: bool = True
    notify_when_up: bool = True
    notify_when_slow: bool = False

    # --- CAMPOS OPCIONAIS COM FALLBACK ---
    role: str = "user"
    permissions: Optional[Dict[str, Any]] = Field(default_factory=lambda: DEFAULT_PERMISSIONS.copy())
    feature_flags: Optional[Dict[str, Any]] = Field(default_factory=lambda: DEFAULT_FEATURE_FLAGS.copy())
    reseller_feature_flags: Optional[Dict[str, Any]] = Field(default_factory=lambda: DEFAULT_RESELLER_FEATURE_FLAGS.copy())
    effective_feature_flags: Optional[Dict[str, Any]] = Field(default_factory=lambda: DEFAULT_FEATURE_FLAGS.copy())
    payment_api_settings: Optional[Dict[str, Any]] = Field(default_factory=lambda: DEFAULT_PAYMENT_API_SETTINGS.copy())
    reminder_templates: Optional[Dict[str, Any]] = Field(default_factory=lambda: normalize_reminder_templates(DEFAULT_REMINDER_TEMPLATES))
    reminder_scenarios: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    reminder_media: Optional[Dict[str, Any]] = Field(default_factory=lambda: EMPTY_REMINDER_MEDIA.copy())
    client_limit: int = 0
    is_active: bool = True
    block_reason: Optional[str] = None
    # -------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        """Converte None -> dict padrão antes de qualquer validação de campo."""
        def _coerce(value, default):
            if value is None or not isinstance(value, dict):
                return default.copy()
            return value

        if hasattr(data, "__dict__"):
            # SQLAlchemy ORM object
            obj = data
            # Ensure effective_feature_flags attribute exists
            if not hasattr(obj, "effective_feature_flags"):
                object.__setattr__(obj, "effective_feature_flags", DEFAULT_FEATURE_FLAGS.copy())
            return {
                "id": getattr(obj, "id", None),
                "name": getattr(obj, "name", ""),
                "email": getattr(obj, "email", ""),
                "whatsapp_connected": bool(getattr(obj, "whatsapp_instance", None)),
                "notifications_enabled": getattr(obj, "notifications_enabled", True) if getattr(obj, "notifications_enabled", True) is not None else True,
                "whatsapp_number": getattr(obj, "whatsapp_number", None),
                "whatsapp_instance": getattr(obj, "whatsapp_instance", None),
                "telegram_token": getattr(obj, "telegram_token", None),
                "telegram_chat_id": getattr(obj, "telegram_chat_id", None),
                "notify_when_down": getattr(obj, "notify_when_down", True) if getattr(obj, "notify_when_down", True) is not None else True,
                "notify_when_up": getattr(obj, "notify_when_up", True) if getattr(obj, "notify_when_up", True) is not None else True,
                "notify_when_slow": getattr(obj, "notify_when_slow", False) if getattr(obj, "notify_when_slow", False) is not None else False,
                "role": getattr(obj, "role", "user") or "user",
                "permissions": _coerce(getattr(obj, "permissions", None), DEFAULT_PERMISSIONS),
                "feature_flags": _coerce(getattr(obj, "feature_flags", None), DEFAULT_FEATURE_FLAGS),
                "reseller_feature_flags": _coerce(getattr(obj, "reseller_feature_flags", None), DEFAULT_RESELLER_FEATURE_FLAGS),
                "effective_feature_flags": _coerce(getattr(obj, "effective_feature_flags", None), DEFAULT_FEATURE_FLAGS),
                "payment_api_settings": _coerce(getattr(obj, "payment_api_settings", None), DEFAULT_PAYMENT_API_SETTINGS),
                "reminder_templates": normalize_reminder_templates(_coerce(getattr(obj, "payment_api_settings", None), DEFAULT_PAYMENT_API_SETTINGS).get("reminder_templates")),
                "reminder_scenarios": normalize_custom_reminder_scenarios(_coerce(getattr(obj, "payment_api_settings", None), DEFAULT_PAYMENT_API_SETTINGS).get("reminder_scenarios")),
                "reminder_media": normalize_reminder_media(_coerce(getattr(obj, "payment_api_settings", None), DEFAULT_PAYMENT_API_SETTINGS).get("reminder_media")),
                "client_limit": getattr(obj, "client_limit", 0) or 0,
                "is_active": getattr(obj, "is_active", True) if getattr(obj, "is_active", True) is not None else True,
                "block_reason": getattr(obj, "block_reason", None),
            }
        elif isinstance(data, dict):
            data["permissions"] = _coerce(data.get("permissions"), DEFAULT_PERMISSIONS)
            data["feature_flags"] = _coerce(data.get("feature_flags"), DEFAULT_FEATURE_FLAGS)
            data["reseller_feature_flags"] = _coerce(data.get("reseller_feature_flags"), DEFAULT_RESELLER_FEATURE_FLAGS)
            data["effective_feature_flags"] = _coerce(data.get("effective_feature_flags"), DEFAULT_FEATURE_FLAGS)
            data["payment_api_settings"] = _coerce(data.get("payment_api_settings"), DEFAULT_PAYMENT_API_SETTINGS)
            data["reminder_templates"] = normalize_reminder_templates(data["payment_api_settings"].get("reminder_templates"))
            data["reminder_scenarios"] = normalize_custom_reminder_scenarios(data["payment_api_settings"].get("reminder_scenarios"))
            data["reminder_media"] = normalize_reminder_media(data["payment_api_settings"].get("reminder_media"))
        return data

    class Config:
        from_attributes = True
