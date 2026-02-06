# backend/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    # Configurações de WhatsApp
    whatsapp_number = Column(String, nullable=True)
    whatsapp_connected = Column(Boolean, default=False)
    whatsapp_instance = Column(String, nullable=True)

    # Configurações de Telegram (NOVO)
    telegram_token = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)

    # Configurações Globais e Flags de Notificação
    notifications_enabled = Column(Boolean, default=True)

    notify_when_down = Column(Boolean, default=True)
    notify_when_up = Column(Boolean, default=True)
    notify_when_slow = Column(Boolean, default=False)

    urls = relationship("MonitoredURL", back_populates="owner")

# A CLASSE ABAIXO DEVE ESTAR ALINHADA À ESQUERDA (SEM ESPAÇOS NO INÍCIO)
class MonitoredURL(Base):
    __tablename__ = "monitored_urls"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    nickname = Column(String, nullable=True)
    category = Column(String, default="Geral")
    status = Column(String, default="unknown")  # UP, DOWN, WARNING, unknown
    http_code = Column(Integer, nullable=True)
    ip_address = Column(String, nullable=True)
    last_check = Column(DateTime, default=datetime.now)
    response_time = Column(Float, default=0.0)
    error = Column(String, nullable=True)
    error_type = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="urls")