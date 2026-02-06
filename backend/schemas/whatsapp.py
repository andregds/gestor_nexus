# backend/schemas/whatsapp.py
from pydantic import BaseModel
from typing import Optional

class WhatsAppNumber(BaseModel):
    number: str

class WhatsAppConnectResponse(BaseModel):
    success: bool
    message: str
    instance_name: Optional[str] = None
    qr_code: Optional[str] = None # QR Code inicial, se disponível

class WhatsAppStatusResponse(BaseModel):
    connected: bool
    instance_name: Optional[str] = None
    qr_code: Optional[str] = None
    state: str # Ex: CONNECTED, DISCONNECTED, QRCODE, NOT_FOUND, TIMEOUT, ERROR
    message: Optional[str] = None
    whatsapp_number: Optional[str] = None # Para o frontend exibir o número conectado
