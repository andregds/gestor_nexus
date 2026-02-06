# backend/schemas/client.py
from pydantic import BaseModel
from typing import Optional
from datetime import date

class ClientBase(BaseModel):
    name: str
    login: str
    server_name: str
    whatsapp: str
    expiration_date: date
    notes: Optional[str] = None
    m3u8_url: Optional[str] = None
    notify_downtime: bool = True
    reminder_enabled: bool = True
    reminder_days_before: str = "3" # Recebe como string, ex: "1,2,3"
    notify_after_expiration: bool = True

class ClientCreate(ClientBase):
    pass

class ClientResponse(ClientBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True