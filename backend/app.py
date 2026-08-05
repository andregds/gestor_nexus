# backend/app.py
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, HttpUrl
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

# Imports locais
from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from database import Base, engine, get_db
from models import User, MonitoredURL
from monitor import start_monitoring
from whatsapp_utils import send_whatsapp_notification
from routes import whatsapp

load_dotenv()


def ensure_client_error_columns():
    with engine.begin() as connection:
        inspector = inspect(connection)
        client_columns = {column["name"] for column in inspector.get_columns("clients")} if "clients" in inspector.get_table_names() else set()
        if "clients" not in inspector.get_table_names():
            return
        if "plan_price" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN plan_price FLOAT NULL"))
        if "selected_products" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN selected_products JSON NULL"))
        if "reminder_error_message" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN reminder_error_message VARCHAR(500)"))
        if "reminder_error_at" not in client_columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN reminder_error_at DATETIME"))


def ensure_user_schedule_columns():
    with engine.begin() as connection:
        inspector = inspect(connection)
        user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in inspector.get_table_names() else set()
        if "users" not in inspector.get_table_names():
            return
        if "last_reminder_run_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN last_reminder_run_at DATETIME"))


Base.metadata.create_all(bind=engine)
ensure_client_error_columns()
ensure_user_schedule_columns()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando aplicação...")
    app.state.monitoring_task = asyncio.create_task(start_monitoring(None))
    try:
        yield
    finally:
        print("🛑 Desligando aplicação...")
        if hasattr(app.state, 'monitoring_task') and app.state.monitoring_task:
            app.state.monitoring_task.cancel()
            try:
                await app.state.monitoring_task
            except asyncio.CancelledError:
                pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp.router)

# --- Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    whatsapp_number: Optional[str] = None
    whatsapp_connected: bool
    notifications_enabled: bool
    class Config: from_attributes = True

class URLCreate(BaseModel):
    url: HttpUrl
    nickname: Optional[str] = None
    category: Optional[str] = "Geral"

class URLResponse(BaseModel):
    id: int
    url: str
    nickname: Optional[str] = None
    category: str
    status: str
    http_code: Optional[int] = None
    ip_address: Optional[str] = None
    last_check: datetime
    response_time: float
    is_active: bool
    class Config: from_attributes = True

class TestMessage(BaseModel):
    number: str

# --- Rotas ---
@app.post("/register", response_model=UserResponse, status_code=201)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="E-mail já registrado")
    new_user = User(
        name=user.name, email=user.email,
        hashed_password=get_password_hash(user.password),
        notifications_enabled=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/urls", response_model=List[URLResponse])
def get_urls(current_user: User = Depends(get_current_user)):
    return current_user.urls

@app.post("/urls", response_model=URLResponse)
def create_url(url_data: URLCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(MonitoredURL).filter(MonitoredURL.url == str(url_data.url), MonitoredURL.user_id == current_user.id).first():
        raise HTTPException(status_code=400, detail="URL já monitorada.")
    new_url = MonitoredURL(
        url=str(url_data.url), nickname=url_data.nickname,
        category=url_data.category, user_id=current_user.id, status="unknown"
    )
    db.add(new_url)
    db.commit()
    db.refresh(new_url)
    return new_url

@app.delete("/urls/{url_id}", status_code=204)
def delete_url(url_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    url = db.query(MonitoredURL).filter(MonitoredURL.id == url_id, MonitoredURL.user_id == current_user.id).first()
    if not url:
        raise HTTPException(404, "URL não encontrada")
    db.delete(url)
    db.commit()

# ROTA CORRIGIDA
@app.post("/whatsapp/test-notification")
async def test_notification(data: TestMessage, current_user: User = Depends(get_current_user)):
    instance_name = f"monitor_user_{current_user.id}"
    if not data.number or len(data.number) < 10:
        raise HTTPException(status_code=400, detail="Número inválido. Use o formato DDI+DDD+Número.")

    message = "🔔 *Teste de Notificação*\\n\\nO sistema de monitoramento está conectado e enviando mensagens com sucesso! 🚀"
    result = await send_whatsapp_notification(data.number, message, instance_name)

    if result.get("accepted"):
        if result.get("delivered"):
            return {"message": "Mensagem entregue com sucesso!", "delivery_confirmed": True}
        return {
            "message": f"Mensagem aceita pela WAHA e aguardando confirmação de entrega (status atual: {result.get('gateway_status')}).",
            "delivery_confirmed": False,
            "gateway_status": result.get("gateway_status"),
        }

    # ESTA É A CORREÇÃO: Retorna 400 em vez de 500
    raise HTTPException(status_code=400, detail="Falha no envio. Verifique se o número possui WhatsApp válido.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
