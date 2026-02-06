# backend/models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, DateTime, JSON
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    # Configurações do WhatsApp
    whatsapp_number = Column(String, nullable=True)
    whatsapp_instance = Column(String, nullable=True)
    whatsapp_apikey = Column(String, nullable=True)
    notification_channel = Column(String, default="whatsapp")

    # Configurações do Telegram
    telegram_token = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)

    # Flags de Notificação Globais
    notifications_enabled = Column(Boolean, default=True)
    notify_when_down = Column(Boolean, default=True)
    notify_when_up = Column(Boolean, default=True)
    notify_when_slow = Column(Boolean, default=False)

    # NOVO CAMPO: Horário de envio das cobranças (Ex: "09:00")
    notification_time = Column(String, default="09:00", nullable=True)

    # Relacionamentos
    urls = relationship("MonitoredURL", back_populates="owner")
    clients = relationship("Client", back_populates="owner")

    # --- PROPRIEDADE VIRTUAL CORRIGIDA ---
    @property
    def whatsapp_connected(self) -> bool:
        """
        Retorna True se o usuário tiver uma instância de WhatsApp criada.
        Não depende mais do whatsapp_number, permitindo envio para terceiros
        mesmo sem o número do admin salvo.
        """
        return bool(self.whatsapp_instance)
    # --------------------------------------


class MonitoredURL(Base):
    __tablename__ = "monitored_urls"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    nickname = Column(String, nullable=True)
    status = Column(String, default="PENDING")
    http_code = Column(Integer, nullable=True)
    response_time = Column(Integer, nullable=True)
    ip_address = Column(String, nullable=True)

    # CORREÇÃO: Alterado de Date para DateTime para salvar horas/minutos/segundos
    last_check = Column(DateTime, nullable=True)

    error = Column(String, nullable=True)
    error_type = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="urls")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    login = Column(String, index=True)
    server_name = Column(String)
    whatsapp = Column(String)

    # Mantido como Date, pois validade de assinatura geralmente não precisa de hora exata
    expiration_date = Column(Date)

    notes = Column(String, nullable=True)
    m3u8_url = Column(String, nullable=True)

    # NOVO CAMPO: Para salvar campos dinâmicos (ex: {"MAC": "00:11...", "App": "IPTV Smarters"})
    custom_fields = Column(JSON, nullable=True)

    # --- NOVO CAMPO ADICIONADO ---
    # Canal preferencial de notificação: 'whatsapp', 'telegram', etc.
    notification_channel = Column(String, default="whatsapp")
    # -----------------------------

    # Flags
    notify_downtime = Column(Boolean, default=True)
    reminder_enabled = Column(Boolean, default=True)
    reminder_days_before = Column(String, default="3")
    notify_after_expiration = Column(Boolean, default=True)

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="clients")