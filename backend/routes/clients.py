# backend/routes/clients.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, datetime
import asyncio
from zoneinfo import ZoneInfo  # Import essencial para corrigir o Fuso Horário
import os

# --- IMPORTS DE DEPENDÊNCIAS ---
from core.dependencies import get_db, get_current_user
from models import User, Client
from telegram_utils import send_telegram_message
from routes import messages as messages_route  # NOVO IMPORT PARA MENSAGENS
from core.security import verify_password # Import for password verification

# --- IMPORTAÇÃO DA FUNÇÃO CORRETA DE WHATSAPP ---
from whatsapp_utils import send_whatsapp_notification, send_whatsapp_image

router = APIRouter(prefix="/clients", tags=["Clientes"])


# --- SCHEMAS ---

class PasswordConfirmation(BaseModel):
    password: str

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
        from_attributes = True  # <--- CORRIGIDO AQUI (Era orm_mode = True)


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
    Suporta filtros: 'default', 'expired', '0', '1', '2', '3', 'msg_ID'.
    """
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()

    # --- CORREÇÃO DE FUSO HORÁRIO (BRASIL) ---
    try:
        tz_brazil = ZoneInfo("America/Sao_Paulo")
    except Exception:
        # Fallback caso o sistema não tenha tzdata (comum em Windows sem config)
        print("⚠️ Aviso: ZoneInfo não encontrado, usando sistema local.")
        tz_brazil = None

    if tz_brazil:
        today = datetime.now(tz_brazil).date()
    else:
        today = datetime.now().date()
    # -----------------------------------------

    selected_filter = str(filter_type or "default")
    is_custom_message = selected_filter.startswith('msg_')
    allowed_filters = {"default", "expired", "0", "1", "2", "3", "4"}
    if not is_custom_message and selected_filter not in allowed_filters:
        raise HTTPException(status_code=400, detail="Filtro de envio inválido.")
    custom_message = None
    if is_custom_message:
        try:
            msg_id = int(selected_filter.replace('msg_', ''))
            custom_message = next((m for m in messages_route.messages if m.get('id') == msg_id), None)
        except Exception:
            custom_message = None
        if not custom_message:
            raise HTTPException(status_code=400, detail="Mensagem personalizada não encontrada para envio em massa.")

    sent_count = 0
    print(f"\n--- INICIANDO ENVIO EM MASSA ---")
    print(f"📅 Data considerada HOJE (BR): {today}")
    print(f"🔍 Filtro Selecionado: {selected_filter}")
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
        msg_type = None
        if is_custom_message:
            # Mensagem personalizada: apenas clientes não vencidos
            if days_diff >= 0:
                should_send = True
        else:
            if selected_filter == "default":
                try:
                    threshold = int(client.reminder_days_before)
                except (ValueError, TypeError):
                    threshold = 3
                if 0 <= days_diff <= threshold:
                    should_send = True
                elif days_diff < 0 and client.notify_after_expiration:
                    should_send = True
            elif selected_filter == "expired":
                should_send = days_diff < 0 and client.notify_after_expiration
            elif selected_filter in {"0", "1", "2", "3", "4"}:
                try:
                    target_day = int(selected_filter)
                except ValueError:
                    target_day = None
                if target_day is not None and days_diff == target_day:
                    should_send = True
            # Demais filtros desconhecidos não enviam
        if not should_send:
            continue

        # Lógica estrita para o tipo de mensagem (somente para filtros aplicáveis)
        if not is_custom_message:
            if days_diff == 0:
                msg_type = "vence_1"
            elif days_diff == 1:
                msg_type = "vence_2"
            elif days_diff == 2:
                msg_type = "vence_3"
            elif days_diff == 3:
                msg_type = "vence_4"
            elif days_diff < 0:
                msg_type = "vencido"
            else:
                msg_type = None
        print(f"✅ Processando envio para: {client.name} (Vence em {days_diff} dias)")

        # Busca mensagem pré-pronta
        msg = None
        image_path = None
        if is_custom_message:
            msg = custom_message['content']
            image_path = custom_message.get('image')
        else:
            for m in messages_route.messages:
                if m["type"] == msg_type:
                    msg = render_message_template(m["content"], client, days_diff)
                    if m.get("image"):
                        # Caminho absoluto ao projeto
                        rel_path = m["image"].lstrip("/")
                        abs_path = os.path.join(os.getcwd(), rel_path)
                        if os.path.isfile(abs_path):
                            image_path = abs_path
                        else:
                            image_path = None
                    break
        if not msg:
            if days_diff == 0:
                msg = f"Olá {client.name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
            elif days_diff == 1:
                msg = f"Olá {client.name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
            elif days_diff > 1:
                msg = f"Olá {client.name}! 📅 Sua assinatura vence em {days_diff} dias. Evite bloqueios!"
            elif days_diff < 0:
                days_overdue = abs(days_diff)
                msg = f"Olá {client.name}. ❌ Sua assinatura venceu há {days_overdue} dias. Entre em contato para reativar."
        # --- ENVIO ---
        channel = client.notification_channel or "whatsapp"
        success = False
        # Envio WhatsApp
        if channel == "whatsapp" and has_whatsapp:
            try:
                if image_path:
                    success = await send_whatsapp_image(
                        number=client.whatsapp,
                        image_path=image_path,
                        caption=msg,
                        instance_name=current_user.whatsapp_instance
                    )
                else:
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


@router.post("/delete-all", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_clients(
    confirmation: PasswordConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Deleta TODOS os clientes de um usuário após confirmar a senha.
    """
    # 1. Verificar a senha do usuário
    if not verify_password(confirmation.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha incorreta. A exclusão não foi realizada.",
        )

    # 2. Se a senha estiver correta, apagar os clientes
    try:
        num_deleted = db.query(Client).filter(Client.owner_id == current_user.id).delete(synchronize_session=False)
        db.commit()
        print(f"Usuário {current_user.email} deletou {num_deleted} clientes.")
    except Exception as e:
        db.rollback()
        print(f"Erro ao deletar clientes para o usuário {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro no servidor ao tentar apagar os clientes."
        )

    return None


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
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    days_diff = (client.expiration_date - today).days

    # Busca mensagem pré-pronta igual ao agendador
    def get_predefined_message_and_image(days_diff, client_name):
        if days_diff < 0:
            msg_type = "vencido"
        elif days_diff == 0:
            msg_type = "vence_1"
        elif days_diff == 1:
            msg_type = "vence_2"
        elif days_diff == 2:
            msg_type = "vence_3"
        elif days_diff == 3:
            msg_type = "vence_4"
        else:
            msg_type = None
        if not msg_type:
            return None, None
        for msg in messages_route.messages:
            if msg["type"] == msg_type:
                image_path = msg.get("image")
                if image_path:
                    image_path = image_path.lstrip("/")
                    if not os.path.isfile(image_path):
                        image_path = None
                return msg["content"].replace("{cliente}", client_name), image_path
        return None, None

    msg, image_path = get_predefined_message_and_image(days_diff, client.name)
    if not msg:
        # fallback antigo
        if days_diff == 0:
            msg = f"Olá {client.name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
        elif days_diff == 1:
            msg = f"Olá {client.name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
        elif days_diff > 1:
            msg = f"Olá {client.name}! 📅 Sua assinatura vence em {days_diff} dias. Evite bloqueios!"
        elif days_diff < 0:
            days_overdue = abs(days_diff)
            msg = f"Olá {client.name}. ❌ Sua assinatura venceu há {days_overdue} dias. Entre em contato para reativar."
    else:
        msg = render_message_template(msg, client, days_diff)

    # Definição do canal
    channel = client.notification_channel or "whatsapp"
    success = False
    error_detail = ""

    # --- ENVIO VIA WHATSAPP ---
    if channel == "whatsapp":
        if not current_user.whatsapp_connected:
            raise HTTPException(status_code=400, detail="WhatsApp não conectado. Configure na aba Integração.")

        try:
            if image_path:
                success = await send_whatsapp_image(
                    number=client.whatsapp,
                    image_path=image_path,
                    caption=msg,
                    instance_name=current_user.whatsapp_instance
                )
            else:
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


# Função utilitária para substituir variáveis na mensagem

def render_message_template(template, client, days_diff=None):
    valor = getattr(client, 'valor', '') if hasattr(client, 'valor') else ''
    vencimento = getattr(client, 'expiration_date', '') if hasattr(client, 'expiration_date') else ''
    login = getattr(client, 'login', '') if hasattr(client, 'login') else ''
    whatsapp = getattr(client, 'whatsapp', '') if hasattr(client, 'whatsapp') else ''
    return (
        template
        .replace('{cliente}', client.name)
        .replace('{dias}', str(days_diff) if days_diff is not None else '')
        .replace('{valor}', str(valor))
        .replace('{vencimento}', str(vencimento))
        .replace('{login}', str(login))
        .replace('{whatsapp}', str(whatsapp))
    )

# Exemplo de uso na função de envio manual e agendado:
# msg = render_message_template(msg["content"], client, days_diff)
