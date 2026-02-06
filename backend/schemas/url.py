# backend/schemas/url.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class URLBase(BaseModel):
    url: str
    nickname: Optional[str] = None


class URLCreate(URLBase):
    pass


class URLResponse(URLBase):
    id: int
    user_id: int
    status: str
    is_active: bool

    # Adicionando os campos que estavam faltando para o Dashboard
    http_code: Optional[int] = None
    response_time: Optional[float] = None
    ip_address: Optional[str] = None
    last_check: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True