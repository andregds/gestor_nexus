# backend/routes/whatsapp.py
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

# Imports do projeto
from database import get_db
from auth import get_current_user
from models import User
from core.config import (
    get_public_backend_url,
    get_waha_api_key,
    get_waha_api_url,
)
from whatsapp_utils import (
    configure_waha_webhook,
    create_whatsapp_session,
    delete_whatsapp_session,
    generate_instance_name,
    get_instance_state_and_qr,
    send_whatsapp_notification,
)

# Configura o logger para ser mais útil
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/whatsapp",
    tags=["WhatsApp"],
    dependencies=[Depends(get_current_user)],
)
webhook_router = APIRouter(tags=["WhatsApp Webhooks"])


# --- HELPER PARA QR CODE ---
def format_qr_code(base64_code: str) -> Optional[str]:
    if not base64_code:
        return None
    # O frontend já espera o prefixo, então garantimos que ele sempre esteja lá
    if base64_code.startswith("data:image/"):
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
    webhook_url: Optional[str] = None
    webhook_configured: bool = False
    webhook_warning: Optional[str] = None


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    instance_name: Optional[str]
    qr_code: Optional[str]
    state: str
    whatsapp_number: Optional[str]


class TestNotificationRequest(BaseModel):
    number: Optional[str] = None


def _is_publicly_reachable_host(hostname: str) -> bool:
    normalized = str(hostname or "").strip().lower()
    return normalized not in {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_waha_configured() -> bool:
    return bool(get_waha_api_url() and get_waha_api_key())


def _resolve_waha_webhook_url(request: Request) -> tuple[Optional[str], Optional[str]]:
    explicit_base_url = get_public_backend_url()
    if explicit_base_url:
        return f"{explicit_base_url}/v1/webhooks/waha/whatsapp", None

    request_base_url = str(request.base_url).rstrip("/")
    if _is_publicly_reachable_host(request.url.hostname or ""):
        return f"{request_base_url}/v1/webhooks/waha/whatsapp", None

    return (
        None,
        "Webhook da WAHA não configurado automaticamente porque esta API está em localhost. "
        "Defina BACKEND_PUBLIC_URL ou APP_PUBLIC_URL com uma URL pública para receber eventos de entrega.",
    )


def _extract_event_name(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("event", "type", "eventName"):
            value = payload.get(key)
            if value:
                return str(value)
    return "UNKNOWN"


def _extract_instance_name(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    if payload.get("session"):
        return str(payload.get("session"))
    if payload.get("name"):
        return str(payload.get("name"))
    if payload.get("instanceName"):
        return str(payload.get("instanceName"))
    instance = payload.get("instance")
    if isinstance(instance, dict) and instance.get("instanceName"):
        return str(instance.get("instanceName"))
    data = payload.get("data")
    if isinstance(data, dict):
        if data.get("instanceName"):
            return str(data.get("instanceName"))
        instance_data = data.get("instance")
        if isinstance(instance_data, dict) and instance_data.get("instanceName"):
            return str(instance_data.get("instanceName"))
    return None


def _extract_message_status(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ("status", "ack", "messageStatus"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "ack", "messageStatus"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
    return None


# --- ROTAS ---

@router.post("/connect", response_model=WhatsAppConnectResponse)
async def connect_whatsapp(
        request: Request,
        whatsapp_data: WhatsAppNumber,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    logger.info(
        "[WHATSAPP][ROUTE] connect iniciado | user_id=%s | has_instance=%s | number=%s",
        current_user.id,
        bool(current_user.whatsapp_instance),
        whatsapp_data.number,
    )
    if not _is_waha_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API WAHA não configurada no servidor. Defina WAHA_API_URL e WAHA_API_KEY.",
        )

    # 1. Limpeza de instância anterior (se existir)
    if current_user.whatsapp_instance:
        logger.info(f"Removendo instância antiga: {current_user.whatsapp_instance}")
        try:
            await delete_whatsapp_session(current_user.whatsapp_instance)
        except Exception as e:
            # Loga o erro mas continua o processo, pois o objetivo é criar uma nova
            logger.error(f"Falha ao remover instância antiga (não bloqueante): {e}")
        current_user.whatsapp_instance = None
        # REMOVIDO: Atribuição a current_user.whatsapp_connected

    # 2. Criação da nova instância
    instance_name = generate_instance_name(current_user)
    logger.info(f"Criando nova instância: {instance_name}")
    success = await create_whatsapp_session(instance_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao criar sessão na WAHA.",
        )

    current_user.whatsapp_instance = instance_name
    if whatsapp_data.number:
        current_user.whatsapp_number = whatsapp_data.number

    # 3. Commit único no banco de dados
    db.commit()

    webhook_url = None
    webhook_configured = False
    webhook_warning = None
    resolved_webhook_url, resolution_warning = _resolve_waha_webhook_url(request)
    if resolved_webhook_url:
        webhook_url = resolved_webhook_url
        try:
            webhook_result = await configure_waha_webhook(instance_name, resolved_webhook_url)
            webhook_configured = True
            logger.info(
                "[WHATSAPP][ROUTE] webhook configurado | user_id=%s | instance=%s | webhook_url=%s | result=%s",
                current_user.id,
                instance_name,
                resolved_webhook_url,
                webhook_result,
            )
        except Exception as exc:
            webhook_warning = str(exc)
            logger.warning(
                "[WHATSAPP][ROUTE] falha ao configurar webhook | user_id=%s | instance=%s | webhook_url=%s | erro=%s",
                current_user.id,
                instance_name,
                resolved_webhook_url,
                exc,
            )
    else:
        webhook_warning = resolution_warning

    # 4. Obter QR Code inicial
    status_info = await get_instance_state_and_qr(instance_name)
    qr_code_raw = status_info.get("qr_code")
    logger.info(
        "[WHATSAPP][ROUTE] connect finalizado | user_id=%s | instance=%s | state=%s | has_qr=%s",
        current_user.id,
        instance_name,
        status_info.get("state"),
        bool(qr_code_raw),
    )

    return WhatsAppConnectResponse(
        success=True,
        message="Sessão WAHA criada com sucesso. Aguardando QR Code.",
        instance_name=instance_name,
        qr_code=format_qr_code(qr_code_raw),
        webhook_url=webhook_url,
        webhook_configured=webhook_configured,
        webhook_warning=webhook_warning,
    )


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
        current_user: User = Depends(get_current_user),
):
    logger.info(
        "[WHATSAPP][ROUTE] status solicitado | user_id=%s | instance=%s",
        current_user.id,
        current_user.whatsapp_instance,
    )
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
    logger.info(
        "[WHATSAPP][ROUTE] status respondido | user_id=%s | instance=%s | state=%s | connected=%s | has_qr=%s",
        current_user.id,
        current_user.whatsapp_instance,
        state,
        connected,
        bool(qr_code_raw),
    )

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
    logger.info(
        "[WHATSAPP][ROUTE] disconnect iniciado | user_id=%s | instance=%s",
        current_user.id,
        current_user.whatsapp_instance,
    )
    if not current_user.whatsapp_instance:
        return {"success": True, "message": "Nenhuma instância para desconectar."}

    instance_to_delete = current_user.whatsapp_instance
    logger.info(f"Desconectando instância: {instance_to_delete}")

    await delete_whatsapp_session(instance_to_delete)

    current_user.whatsapp_instance = None
    current_user.whatsapp_number = None # Opcional: limpar o número ao desconectar
    # REMOVIDO: Atribuição a current_user.whatsapp_connected

    db.commit()
    logger.info(
        "[WHATSAPP][ROUTE] disconnect finalizado | user_id=%s | instance=%s",
        current_user.id,
        instance_to_delete,
    )
    return {"success": True, "message": "Instância desconectada com sucesso."}


@router.post("/test-notification")
async def test_whatsapp_notification_route(
        request: TestNotificationRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    logger.info(
        "[WHATSAPP][ROUTE] test-notification iniciado | user_id=%s | instance=%s | request_number=%s",
        current_user.id,
        current_user.whatsapp_instance,
        request.number,
    )
    # A verificação agora usa a propriedade dinâmica, que é mais confiável
    if not current_user.whatsapp_connected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp não está conectado.")

    target_number = request.number or current_user.whatsapp_number
    if not target_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum número de destino informado.")

    result = await send_whatsapp_notification(
        target_number,
        "🚀 Teste de notificação do Gestor Nexus!",
        current_user.whatsapp_instance
    )

    if result.get("accepted"):
        logger.info(
            "[WHATSAPP][ROUTE] test-notification aceito | user_id=%s | instance=%s | target=%s | gateway_status=%s | delivered=%s",
            current_user.id,
            current_user.whatsapp_instance,
            target_number,
            result.get("gateway_status"),
            result.get("delivered"),
        )
        if result.get("delivered"):
            return {"success": True, "message": f"Mensagem entregue para {target_number}.", "delivery_confirmed": True}
        return {
            "success": True,
            "message": f"Mensagem aceita pela WAHA para {target_number} e aguardando confirmação de entrega (status atual: {result.get('gateway_status')}).",
            "delivery_confirmed": False,
            "gateway_status": result.get("gateway_status"),
        }

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha no envio. Verifique o console do servidor e se o número é válido.")


@webhook_router.post("/v1/webhooks/waha/whatsapp", name="waha_whatsapp_webhook")
async def waha_whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw_body": (await request.body()).decode("utf-8", errors="ignore")}

    event_name = _extract_event_name(payload)
    instance_name = _extract_instance_name(payload)
    message_status = _extract_message_status(payload)

    logger.info(
        "[WHATSAPP][WEBHOOK] evento recebido | event=%s | instance=%s | message_status=%s | payload=%s",
        event_name,
        instance_name,
        message_status,
        payload,
    )

    return {"success": True, "received": True, "event": event_name}
