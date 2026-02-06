# backend/routes/whatsapp.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import os
from dotenv import load_dotenv

# Imports do projeto
from database import get_db
from auth import get_current_user
from models import User

# CORREÇÃO: Importando funções utilitárias da raiz (sem 'backend.')
from whatsapp_utils import (
    generate_instance_name,
    evolution_delete_instance,
    evolution_create_instance,
    get_instance_state_and_qr,
    send_whatsapp_notification,
)

load_dotenv()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/whatsapp",
    tags=["WhatsApp"],
    dependencies=[Depends(get_current_user)],
)


# --- HELPER PARA QR CODE ---
def format_qr_code(base64_code: str) -> Optional[str]:
    if not base64_code:
        return None
    if base64_code.startswith("data:"):
        return base64_code
    return f"data:image/png;base64,{base64_code}"


# --- SCHEMAS ---
class WhatsAppNumber(BaseModel):
    number: Optional[str] = None


class WhatsAppConnectResponse(BaseModel):
    success: bool
    message: str
    instance_name: str
    qr_code: Optional[str] = None


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    instance_name: Optional[str]
    qr_code: Optional[str]
    state: str
    message: str
    whatsapp_number: Optional[str]


class TestNotificationRequest(BaseModel):
    number: Optional[str] = None


# --- ROTAS ---

@router.post("/connect", response_model=WhatsAppConnectResponse)
async def connect_whatsapp(
        whatsapp_data: WhatsAppNumber,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        raise HTTPException(status_code=503, detail="API Evolution não configurada.")

    # REMOVIDO: Validação de número obrigatório
    # if not whatsapp_data.number:
    #     raise HTTPException(status_code=400, detail="Número obrigatório.")

    # 1. Limpeza anterior
    if current_user.whatsapp_instance:
        try:
            await evolution_delete_instance(current_user.whatsapp_instance)
        except Exception:
            pass
        current_user.whatsapp_instance = None
        current_user.whatsapp_connected = False
        db.commit()

    # 2. Criação
    instance_name = generate_instance_name(current_user)
    success = await evolution_create_instance(instance_name)

    if not success:
        raise HTTPException(status_code=500, detail="Falha ao criar instância.")

    current_user.whatsapp_instance = instance_name

    # Atualiza o número apenas se foi fornecido
    if whatsapp_data.number:
        current_user.whatsapp_number = whatsapp_data.number

    db.commit()

    # 3. Obter QR Code
    status_info = await get_instance_state_and_qr(instance_name)
    qr_code_raw = status_info.get("qr_code")

    return WhatsAppConnectResponse(
        success=True,
        message="Instância criada.",
        instance_name=instance_name,
        qr_code=format_qr_code(qr_code_raw)
    )


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    if not current_user.whatsapp_instance:
        return WhatsAppStatusResponse(
            connected=False, instance_name=None, qr_code=None,
            state="DISCONNECTED", message="Não configurado.", whatsapp_number=None
        )

    status_info = await get_instance_state_and_qr(current_user.whatsapp_instance)
    state = status_info.get("state", "UNKNOWN")
    qr_code_raw = status_info.get("qr_code")

    connected = (state == "open" or state == "connected")

    if current_user.whatsapp_connected != connected:
        current_user.whatsapp_connected = connected
        db.commit()

    msg = "Conectado!" if connected else "Escaneie o QR Code."

    return WhatsAppStatusResponse(
        connected=connected,
        instance_name=current_user.whatsapp_instance,
        qr_code=format_qr_code(qr_code_raw),
        state=state,
        message=msg,
        whatsapp_number=current_user.whatsapp_number
    )


@router.post("/disconnect")
async def disconnect_whatsapp(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    if current_user.whatsapp_instance:
        await evolution_delete_instance(current_user.whatsapp_instance)
        current_user.whatsapp_instance = None
        current_user.whatsapp_connected = False
        current_user.whatsapp_number = None
        db.commit()
    return {"success": True, "message": "Desconectado."}


@router.post("/test-notification")
async def test_whatsapp_notification_route(
        request: TestNotificationRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    if not current_user.whatsapp_connected:
        raise HTTPException(status_code=400, detail="WhatsApp desconectado.")

    # Define qual número usar: o enviado no teste OU o salvo no banco
    target_number = request.number if request.number else current_user.whatsapp_number

    if not target_number:
        raise HTTPException(status_code=400, detail="Nenhum número informado para envio.")

    # (Opcional) Se o usuário enviou um número agora e não tinha nada salvo, podemos salvar agora
    if request.number and not current_user.whatsapp_number:
        current_user.whatsapp_number = request.number
        db.commit()

    success = await send_whatsapp_notification(
        target_number,
        "🚀 Teste de notificação Monitor DNS!",
        current_user.whatsapp_instance
    )

    if success:
        return {"success": True, "message": f"Enviado para {target_number}."}

    raise HTTPException(status_code=500, detail="Falha no envio. Verifique se o número é válido.")