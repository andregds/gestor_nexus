# backend/models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, DateTime, JSON, Float
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.mutable import MutableDict
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    is_active = Column(Boolean, default=True)
    block_reason = Column(String(255), nullable=True)
    role = Column(String(50), default="user")

    permissions = Column(JSON, default={
        "can_view_dashboard": True,
        "can_view_clients": True,
        "can_view_integrations": True,
        "can_view_settings": True
    })

    # Feature flags controlam visibilidade de menus/páginas por usuário
    feature_flags = Column(MutableDict.as_mutable(JSON), default=lambda: {
        "dashboard": True,
        "clients": True,
        "products": True,
        "whatsapp": True,
        "telegram": True,
        "settings": True,
        "resell": False,
        "admin": False,
    })

    # Padrão opcional aplicado aos filhos de um revendedor (herdado quando não houver override no filho)
    reseller_feature_flags = Column(MutableDict.as_mutable(JSON), default=lambda: {
        "dashboard": True,
        "clients": True,
        "products": True,
        "whatsapp": True,
        "telegram": True,
        "settings": True,
        "resell": False,
        "admin": False,
    })

    client_limit = Column(Integer, default=0)

    # Configurações do WhatsApp
    whatsapp_number = Column(String(50), nullable=True)
    whatsapp_instance = Column(String(100), nullable=True)
    whatsapp_apikey = Column(String(255), nullable=True)
    notification_channel = Column(String(50), default="whatsapp")

    # Configurações do Telegram
    telegram_token = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(100), nullable=True)

    # Flags de Notificação
    notifications_enabled = Column(Boolean, default=True)
    notify_when_down = Column(Boolean, default=True)
    notify_when_up = Column(Boolean, default=True)
    notify_when_slow = Column(Boolean, default=False)
    notification_time = Column(String(10), default="09:00", nullable=True)

    # --- NOVO CAMPO: HIERARQUIA (PAI -> FILHO) ---
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    children = relationship("User", backref=backref('owner', remote_side=[id]))
    # ---------------------------------------------

    urls = relationship("MonitoredURL", back_populates="owner")
    clients = relationship("Client", back_populates="owner")

    @property
    def whatsapp_connected(self) -> bool:
        return bool(self.whatsapp_instance)


class MonitoredURL(Base):
    __tablename__ = "monitored_urls"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), index=True)
    nickname = Column(String(100), nullable=True)
    status = Column(String(50), default="PENDING")
    http_code = Column(Integer, nullable=True)
    response_time = Column(Float, nullable=True)
    ip_address = Column(String(50), nullable=True)
    last_check = Column(DateTime, nullable=True)
    error = Column(String(500), nullable=True)
    error_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="urls")


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    login = Column(String(100), index=True)
    server_name = Column(String(100))
    whatsapp = Column(String(50))
    expiration_date = Column(Date)
    notes = Column(String(500), nullable=True)
    m3u8_url = Column(String(500), nullable=True)
    custom_fields = Column(JSON, nullable=True)
    notification_channel = Column(String(50), default="whatsapp")
    notify_downtime = Column(Boolean, default=True)
    reminder_enabled = Column(Boolean, default=True)
    reminder_days_before = Column(String(10), default="3")
    notify_after_expiration = Column(Boolean, default=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="clients")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_type = Column(String(50), index=True, unique=True)
    content = Column(String(1024))
    image_path = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    owner = relationship("User")


# ==================================================
# NOVOS MODELOS PARA PRODUTOS, PLANOS, ETC.
# ==================================================

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True, unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User")
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    description = Column(String(1024), nullable=True)
    price = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User")
    category = relationship("Category", back_populates="products")


class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    price = Column(Float, nullable=False)
    billing_cycle = Column(String(50), nullable=False)  # e.g., "monthly", "yearly"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User")
    features = relationship("Feature", secondary="plan_features", back_populates="plans")


class Feature(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User")
    plans = relationship("Plan", secondary="plan_features", back_populates="features")


class PlanFeature(Base):
    __tablename__ = "plan_features"
    plan_id = Column(Integer, ForeignKey("plans.id"), primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id"), primary_key=True)
