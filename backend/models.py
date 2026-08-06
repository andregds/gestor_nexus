# backend/models.py
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, DateTime, JSON, Float, Text
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))

    # Controle de acesso / hierarquia
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)
    block_reason = Column(String(255), nullable=True)
    client_limit = Column(Integer, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Permissões e feature flags (armazenados como JSON)
    permissions = Column(JSON, default={
        "can_view_dashboard": True,
        "can_view_clients": True,
        "can_view_integrations": True,
        "can_view_settings": True,
    })
    feature_flags = Column(JSON, default={
        "dashboard": True,
        "clients": True,
        "products": True,
        "communication": True,
        "whatsapp": True,
        "telegram": True,
        "settings": True,
        "resell": True,
        "admin": False,
    })
    reseller_feature_flags = Column(JSON, default={
        "dashboard": True,
        "clients": True,
        "products": True,
        "communication": True,
        "whatsapp": True,
        "telegram": True,
        "settings": True,
        "resell": True,
        "admin": False,
    })

    # Configurações do WhatsApp
    whatsapp_number = Column(String(50), nullable=True)
    whatsapp_instance = Column(String(100), nullable=True)
    whatsapp_apikey = Column(String(255), nullable=True)
    notification_channel = Column(String(50), default="whatsapp")

    # Configurações do Telegram
    telegram_token = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(100), nullable=True)

    # Flags de Notificação Globais
    notifications_enabled = Column(Boolean, default=True)
    notify_when_down = Column(Boolean, default=True)
    notify_when_up = Column(Boolean, default=True)
    notify_when_slow = Column(Boolean, default=False)

    # NOVO CAMPO: Horário de envio das cobranças (Ex: "09:00")
    notification_time = Column(String(10), default="09:00", nullable=True)
    last_reminder_run_at = Column(DateTime, nullable=True)

    # Configuração de pagamento por usuário (JSON)
    payment_api_settings = Column(JSON, default={
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
        "pagbank_environment": "production",
        "pagbank_access_token": "",
        "pagbank_webhook_url": "",
        "mercadopago_checkout_mode": "production",
        "mercadopago_access_token": "",
        "mercadopago_public_key": "",
        "mercadopago_webhook_url": "",
        "mercadopago_success_url": "",
        "mercadopago_pending_url": "",
        "mercadopago_failure_url": "",
        "mercadopago_statement_descriptor": "",
    })

    # Plano selecionado / período de teste / renovação
    selected_plan = Column(String(100), nullable=True)
    selected_plan_label = Column(String(255), nullable=True)
    selected_plan_price = Column(Float, nullable=True)
    trial_started_at = Column(DateTime, nullable=True)
    trial_expires_at = Column(DateTime, nullable=True)
    trial_expires_manually_set = Column(Boolean, default=False)
    renewal_order_nsu = Column(String(255), nullable=True)
    renewal_order_created_at = Column(DateTime, nullable=True)
    renewal_invoice_slug = Column(String(255), nullable=True)

    # Relacionamentos
    urls = relationship("MonitoredURL", back_populates="owner")
    clients = relationship("Client", back_populates="owner")
    categories = relationship("Category", back_populates="owner")
    plans = relationship("Plan", back_populates="owner")
    products = relationship("Product", back_populates="owner")

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
    email = Column(String(255), nullable=True)
    server_name = Column(String)
    plan_price = Column(Float, nullable=True)
    selected_products = Column(JSON, nullable=True)
    whatsapp = Column(String)

    # Colunas presentes no banco de dados (produtos / status de pagamento)
    product_id = Column(Integer, nullable=True)
    payment_status = Column(String(20), default="pendente")

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
    reminder_error_message = Column(String(500), nullable=True)
    reminder_error_at = Column(DateTime, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="clients")


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    gateway = Column(String(50), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reference_id = Column(String(255), nullable=False, index=True)
    gateway_order_id = Column(String(255), nullable=True, index=True)
    status = Column(String(50), nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False, default=0)
    customer_name = Column(String(255), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_tax_id = Column(String(20), nullable=True)
    payment_link = Column(String(1200), nullable=True)
    qr_code_text = Column(Text, nullable=True)
    qr_code_image_url = Column(String(1200), nullable=True)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    gateway = Column(String(50), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reference_id = Column(String(255), nullable=True, index=True)
    gateway_order_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(100), nullable=True)
    status = Column(String(50), nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    processed = Column(Boolean, default=False, nullable=False)
    error_message = Column(String(500), nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True, nullable=False)
    description = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    owner = relationship("User", back_populates="categories")
    products = relationship("Product", back_populates="category")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True, nullable=False)
    description = Column(String(500), nullable=True)
    price = Column(Float, nullable=False)
    billing_cycle = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    owner = relationship("User", back_populates="plans")
    products = relationship("Product", back_populates="plan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    description = Column(String(1024), nullable=True)
    price = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    owner = relationship("User", back_populates="products")
    category = relationship("Category", back_populates="products")
    plan = relationship("Plan", back_populates="products")