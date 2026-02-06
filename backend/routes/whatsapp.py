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

# Configura o logger para ser mais útil
logging.basicConfig(level=logging.INFO)
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
    # O frontend já espera o prefixo, então garantimos que ele sempre esteja lá
    if base64_code.startswith("data:image/png;base64,"):
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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API Evolution não configurada no servidor.")

    # 1. Limpeza de instância anterior (se existir)
    if current_user.whatsapp_instance:
        logger.info(f"Removendo instância antiga: {current_user.whatsapp_instance}")
        try:
            await evolution_delete_instance(current_user.whatsapp_instance)
        except Exception as e:
            # Loga o erro mas continua o processo, pois o objetivo é criar uma nova
            logger.error(f"Falha ao remover instância antiga (não bloqueante): {e}")
        current_user.whatsapp_instance = None
        # REMOVIDO: Atribuição a current_user.whatsapp_connected

    # 2. Criação da nova instância
    instance_name = generate_instance_name(current_user)
    logger.info(f"Criando nova instância: {instance_name}")
    success = await evolution_create_instance(instance_name)

    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao criar instância na Evolution API.")

    current_user.whatsapp_instance = instance_name
    if whatsapp_data.number:
        current_user.whatsapp_number = whatsapp_data.number

    # 3. Commit único no banco de dados
    db.commit()

    # 4. Obter QR Code inicial
    status_info = await get_instance_state_and_qr(instance_name)
    qr_code_raw = status_info.get("qr_code")

    return WhatsAppConnectResponse(
        success=True,
        message="Instância criada com sucesso. Aguardando QR Code.",
        instance_name=instance_name,
        qr_code=format_qr_code(qr_code_raw)
    )


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
        current_user: User = Depends(get_current_user),
):
    if not current_user.whatsapp_instance:
        return WhatsAppStatusResponse(
            connected=False, instance_name=None, qr_code=None,
            state="DISCONNECTED", whatsapp_number=None
        )

    status_info = await get_instance_state_and_qr(current_user.whatsapp_instance)
    state = status_info.get("state", "UNKNOWN")
    qr_code_raw = status_info.get("qr_code")

    # A propriedade `whatsapp_connected` no modelo User já faz essa verificação
    # Esta variável `connected` é apenas para uso local na resposta.
    connected = (state == "open")

    # REMOVIDO: Atribuição a current_user.whatsapp_connected

    return WhatsAppStatusResponse(
        connected=connected,
        instance_name=current_user.whatsapp_instance,
        qr_code=format_qr_code(qr_code_raw),
        state=state,
        whatsapp_number=current_user.whatsapp_number
    )


@router.post("/disconnect", status_code=status.HTTP_200_OK)
async def disconnect_whatsapp(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    if not current_user.whatsapp_instance:
        return {"success": True, "message": "Nenhuma instância para desconectar."}

    instance_to_delete = current_user.whatsapp_instance
    logger.info(f"Desconectando instância: {instance_to_delete}")

    await evolution_delete_instance(instance_to_delete)

    current_user.whatsapp_instance = None
    current_user.whatsapp_number = None # Opcional: limpar o número ao desconectar
    # REMOVIDO: Atribuição a current_user.whatsapp_connected

    db.commit()
    return {"success": True, "message": "Instância desconectada com sucesso."}


@router.post("/test-notification")
async def test_whatsapp_notification_route(
        request: TestNotificationRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    # A verificação agora usa a propriedade dinâmica, que é mais confiável
    if not current_user.whatsapp_connected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp não está conectado.")

    target_number = request.number or current_user.whatsapp_number
    if not target_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum número de destino informado.")

    success = await send_whatsapp_notification(
        target_number,
        "🚀 Teste de notificação do Nexus Monitor!",
        current_user.whatsapp_instance
    )

    if success:
        return {"success": True, "message": f"Mensagem de teste enviada para {target_number}."}

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha no envio. Verifique o console do servidor e se o número é válido.")

