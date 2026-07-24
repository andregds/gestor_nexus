# backend/schemas/client.py
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from datetime import date


class ClientBase(BaseModel):
    name: str
    login: str
    server_name: Optional[str] = None
    plan_price: Optional[float] = None
    selected_products: Optional[List[Dict[str, Any]]] = None
    whatsapp: str
    expiration_date: date
    notes: Optional[str] = None
    m3u8_url: Optional[str] = None

    # Campo para dados dinâmicos (ex: MAC, App, etc)
    custom_fields: Optional[Dict[str, Any]] = None

    notify_downtime: bool = True
    reminder_enabled: bool = True
    reminder_days_before: str = "3"
    notify_after_expiration: bool = True

    # Canal de notificação (whatsapp, telegram, etc)
    notification_channel: Optional[str] = "whatsapp"


class ClientCreate(ClientBase):
    pass


class ClientUpdate(ClientBase):
    """Schema específico para atualizações (PUT/PATCH)"""
    pass


class ClientResponse(ClientBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True