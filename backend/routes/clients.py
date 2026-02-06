# backend/routes/clients.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, datetime
import asyncio

# --- IMPORTS DE DEPENDÊNCIAS ---
from core.dependencies import get_db, get_current_user
from models import User, Client
from telegram_utils import send_telegram_message

# --- IMPORTAÇÃO DA FUNÇÃO CORRETA DE WHATSAPP ---
from whatsapp_utils import send_whatsapp_notification

router = APIRouter(prefix="/clients", tags=["Clientes"])


# --- SCHEMAS ---

class ClientCreate(BaseModel):
    name: str
    login: str
    server_name: str
    whatsapp: str
    expiration_date: date
    notes: Optional[str] = None
    m3u8_url: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    notify_downtime: bool = True
    reminder_enabled: bool = True
    reminder_days_before: str = "3"
    notify_after_expiration: bool = True
    notification_channel: Optional[str] = "whatsapp"


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    login: Optional[str] = None
    server_name: Optional[str] = None
    whatsapp: Optional[str] = None
    expiration_date: Optional[date] = None
    notes: Optional[str] = None
    m3u8_url: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    notify_downtime: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    reminder_days_before: Optional[str] = None
    notify_after_expiration: Optional[bool] = None
    notification_channel: Optional[str] = None


class ClientResponse(ClientCreate):
    id: int
    owner_id: int

    class Config:
        orm_mode = True


# ==========================================
# ROTAS ESPECIAIS (DEVEM VIR ANTES DO CRUD)
# ==========================================

@router.post("/process-now")
async def process_reminders_now(
        filter_type: Optional[str] = "default",  # Recebe o filtro do Frontend
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Executa a verificação de cobrança IMEDIATAMENTE.
    Suporta filtros: 'default', 'expired', '0', '1', '2', '3'.
    """
    # Busca todos os clientes do usuário
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()
    today = datetime.now().date()
    sent_count = 0

    print(f"\n--- INICIANDO ENVIO EM MASSA ---")
    print(f"📅 Data do Servidor: {today}")
    print(f"🔍 Filtro Selecionado: {filter_type}")
    print(f"👥 Total de Clientes Analisados: {len(clients)}")

    # Verifica conexão
    has_whatsapp = current_user.whatsapp_connected
    has_telegram = bool(current_user.telegram_token)

    if not has_whatsapp and not has_telegram:
        print("❌ Erro: Nenhum canal conectado.")
        raise HTTPException(status_code=400, detail="Nenhum canal de notificação conectado.")

    for client in clients:
        if not client.reminder_enabled:
            continue

        # Calcula dias para vencer
        days_diff = (client.expiration_date - today).days

        should_send = False
        msg = ""

        # --- LÓGICA DE FILTRAGEM ---

        # 1. Filtro: Vencidos (expired)
        if filter_type == "expired":
            if days_diff < 0:
                should_send = True

        # 2. Filtro: Dias Específicos (0, 1, 2, 3)
        elif filter_type in ["0", "1", "2", "3"]:
            # Converte para int para comparar com days_diff
            target_days = int(filter_type)
            if days_diff == target_days:
                should_send = True
            else:
                # Debug para entender por que não enviou
                # print(f"   Ignorado {client.name}: Faltam {days_diff} dias (Filtro pede {target_days})")
                pass

        # 3. Filtro: Padrão (default) - Respeita a config do cliente
        else:
            try:
                threshold = int(client.reminder_days_before)
            except (ValueError, TypeError):
                threshold = 3

            if 0 <= days_diff <= threshold:
                should_send = True
            elif days_diff < 0 and client.notify_after_expiration:
                should_send = True

        # --- SE PASSOU NO FILTRO, MONTA A MENSAGEM ---
        if should_send:
            print(f"✅ Processando envio para: {client.name} (Vence em {days_diff} dias)")

            if days_diff == 0:
                msg = f"Olá {client.name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
            elif days_diff == 1:
                msg = f"Olá {client.name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
            elif days_diff > 1:
                msg = f"Olá {client.name}! 📅 Sua assinatura vence em {days_diff} dias. Evite bloqueios!"
            else:  # Negativo (Vencido)
                days_overdue = abs(days_diff)
                msg = f"Olá {client.name}. ❌ Sua assinatura venceu há {days_overdue} dias. Entre em contato para reativar."

            # --- ENVIO ---
            channel = client.notification_channel or "whatsapp"
            success = False

            # Envio WhatsApp
            if channel == "whatsapp" and has_whatsapp:
                try:
                    success = await send_whatsapp_notification(
                        number=client.whatsapp,
                        message=msg,
                        instance_name=current_user.whatsapp_instance
                    )
                    if success:
                        print(f"   -> WhatsApp enviado com sucesso!")
                    else:
                        print(f"   -> Falha no envio do WhatsApp (API retornou False)")
                except Exception as e:
                    print(f"   -> Erro técnico no WhatsApp: {e}")
                    success = False

            # Envio Telegram
            elif channel == "telegram" and has_telegram:
                try:
                    await send_telegram_message(
                        token=current_user.telegram_token,
                        chat_id=current_user.telegram_chat_id,
                        message=f"🔔 *Cobrança Manual em Massa: {client.name}*\n\n{msg}"
                    )
                    success = True
                    print(f"   -> Telegram enviado com sucesso!")
                except Exception as e:
                    print(f"   -> Erro técnico no Telegram: {e}")
                    success = False

            if success:
                sent_count += 1
                await asyncio.sleep(1)  # Delay para evitar bloqueio

    print(f"--- FIM DO PROCESSO: {sent_count} enviados ---\n")
    return {"message": f"Processo finalizado! {sent_count} mensagens enviadas.", "sent_count": sent_count}


# ==========================================
# ROTAS CRUD (Create, Read, Update, Delete)
# ==========================================

@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
        client_data: ClientCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    new_client = Client(
        **client_data.dict(),
        owner_id=current_user.id
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return new_client


@router.get("/", response_model=List[ClientResponse])
def read_clients(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    return db.query(Client).filter(Client.owner_id == current_user.id).all()


@router.put("/{client_id}", response_model=ClientResponse)
def update_client(
        client_id: int,
        client_data: ClientUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id, Client.owner_id == current_user.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    update_data = client_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(client, key, value)

    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
        client_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id, Client.owner_id == current_user.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    db.delete(client)
    db.commit()
    return None


# --- ENVIO MANUAL INDIVIDUAL ---

@router.post("/{client_id}/remind")
async def send_manual_reminder(
        client_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Força o envio da mensagem de cobrança para um cliente específico."""

    client = db.query(Client).filter(Client.id == client_id, Client.owner_id == current_user.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    today = datetime.now().date()
    days_diff = (client.expiration_date - today).days
    msg = ""

    # Lógica de mensagens
    if days_diff == 3:
        msg = f"Olá {client.name}! 📅 Sua assinatura vence em 3 dias. Evite bloqueios!"
    elif days_diff == 1:
        msg = f"Olá {client.name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
    elif days_diff == 0:
        msg = f"Olá {client.name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
    elif days_diff < 0:
        msg = f"Olá {client.name}. ❌ Sua assinatura venceu. Entre em contato para reativar."
    else:
        formatted_date = client.expiration_date.strftime('%d/%m/%Y')
        msg = f"Olá {client.name}! 📅 Lembrete: Sua assinatura está ativa e vence dia {formatted_date}."

    # Definição do canal
    channel = client.notification_channel or "whatsapp"
    success = False
    error_detail = ""

    # --- ENVIO VIA WHATSAPP ---
    if channel == "whatsapp":
        if not current_user.whatsapp_connected:
            raise HTTPException(status_code=400, detail="WhatsApp não conectado. Configure na aba Integração.")

        try:
            success = await send_whatsapp_notification(
                number=client.whatsapp,
                message=msg,
                instance_name=current_user.whatsapp_instance
            )
            if not success:
                error_detail = "A Evolution API retornou erro ou falha no envio."
        except Exception as e:
            success = False
            error_detail = str(e)

    # --- ENVIO VIA TELEGRAM ---
    elif channel == "telegram":
        if not current_user.telegram_token:
            raise HTTPException(status_code=400, detail="Telegram não configurado.")

        try:
            await send_telegram_message(
                token=current_user.telegram_token,
                chat_id=current_user.telegram_chat_id,
                message=f"🔔 *Lembrete Manual: {client.name}*\n\n{msg}"
            )
            success = True
        except Exception as e:
            success = False
            error_detail = f"Erro Telegram: {str(e)}"

    if success:
        return {"message": f"Mensagem enviada via {channel}!", "sent": True}
    else:
        print(f"❌ Erro no envio manual: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Falha ao enviar mensagem: {error_detail}")