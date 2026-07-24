# backend/routes/clients.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
import asyncio

# --- IMPORTS DE DEPENDÊNCIAS ---
from core.dependencies import get_db, get_current_user
from models import User, Client
from reminder_utils import build_client_custom_reminder_message, build_client_reminder_message, send_client_reminder

router = APIRouter(prefix="/clients", tags=["Clientes"])


# --- SCHEMAS ---

class ClientCreate(BaseModel):
    name: str
    login: str
    server_name: Optional[str] = None
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
        from_attributes = True


def resolve_days_window(days_ahead: int, today: date) -> tuple[date, date]:
    offset = max(days_ahead - 1, 0)
    return today - timedelta(days=offset), today + timedelta(days=offset)


# ==========================================
# ROTAS ESPECIAIS (DEVEM VIR ANTES DO CRUD)
# ==========================================

@router.post("/process-now")
async def process_reminders_now(
        filter_type: Optional[str] = "default",  # Recebe o filtro do Frontend
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        days_ahead: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Executa a verificação de cobrança IMEDIATAMENTE.
    Suporta filtros: 'default', 'expired', '0', '1', '2', '3' e 'custom:<id>'.
    Quando houver intervalo de vencimento ou quantidade de dias informada, envia apenas para clientes dentro desse recorte.
    No filtro por dias, considera os clientes vencidos recentemente e os que vão vencer
    dentro da mesma janela salva.
    """
    today = datetime.now().date()

    if days_ahead is not None and days_ahead < 0:
        raise HTTPException(status_code=400, detail="A quantidade de dias deve ser igual ou maior que zero.")

    if days_ahead is not None:
        date_from, date_to = resolve_days_window(days_ahead, today)

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="A data inicial não pode ser maior que a data final.")

    clients_query = db.query(Client).filter(Client.owner_id == current_user.id)
    if date_from:
        clients_query = clients_query.filter(Client.expiration_date >= date_from)
    if date_to:
        clients_query = clients_query.filter(Client.expiration_date <= date_to)

    clients = clients_query.all()
    sent_count = 0

    print(f"\n--- INICIANDO ENVIO EM MASSA ---")
    print(f"📅 Data do Servidor: {today}")
    print(f"🔍 Filtro Selecionado: {filter_type}")
    if days_ahead is not None:
        past_days = max(days_ahead - 1, 0)
        if days_ahead <= 1:
            print("⏳ Janela dinâmica aplicada: apenas clientes que vencem hoje")
        else:
            print(
                f"⏳ Janela dinâmica aplicada: clientes vencidos há até {past_days} dia(s) "
                f"e clientes que vencem nos próximos {past_days} dia(s)"
            )
    elif date_from or date_to:
        print(f"🗓️ Intervalo de vencimento aplicado: {date_from or '...'} até {date_to or '...'}")
    print(f"👥 Total de Clientes Analisados: {len(clients)}")

    # Verifica conexão
    has_whatsapp = current_user.whatsapp_connected
    has_telegram = bool(current_user.telegram_token)

    if not has_whatsapp and not has_telegram:
        print("❌ Erro: Nenhum canal conectado.")
        raise HTTPException(status_code=400, detail="Nenhum canal de notificação conectado.")

    custom_scenario_id = None
    custom_scenario_name = ""
    if isinstance(filter_type, str) and filter_type.startswith("custom:"):
        custom_scenario_id = filter_type.split(":", 1)[1].strip()
        if not custom_scenario_id:
            raise HTTPException(status_code=400, detail="Mensagem personalizada inválida.")
        try:
            _, custom_scenario, _ = build_client_custom_reminder_message(
                clients[0] if clients else None,
                current_user,
                0,
                custom_scenario_id,
            )
            custom_scenario_name = str(custom_scenario.get("name", "") or "").strip()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    for client in clients:
        if not client.reminder_enabled:
            continue

        # Calcula dias para vencer
        days_diff = (client.expiration_date - today).days

        should_send = False
        msg = ""
        media = None

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

        # 3. Filtro: Mensagem personalizada
        elif custom_scenario_id:
            should_send = True

        # 4. Filtro: Padrão (default) - Respeita a config do cliente
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

            try:
                if custom_scenario_id:
                    msg, _, media = build_client_custom_reminder_message(client, current_user, days_diff, custom_scenario_id)
                else:
                    msg, _, media = build_client_reminder_message(client, current_user, days_diff)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            # --- ENVIO ---
            channel = client.notification_channel or "whatsapp"
            success = False

            # Envio WhatsApp
            if channel == "whatsapp" and has_whatsapp:
                try:
                    success, _, _ = await send_client_reminder(
                        current_user,
                        client,
                        msg,
                        media=media,
                        telegram_prefix=f"🔔 *Cobrança Manual em Massa: {client.name}*",
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
                    success, _, _ = await send_client_reminder(
                        current_user,
                        client,
                        msg,
                        media=media,
                        telegram_prefix=f"🔔 *Cobrança Manual em Massa: {client.name}*",
                    )
                    print(f"   -> Telegram enviado com sucesso!")
                except Exception as e:
                    print(f"   -> Erro técnico no Telegram: {e}")
                    success = False

            if success:
                sent_count += 1
                await asyncio.sleep(1)  # Delay para evitar bloqueio
 
    print(f"--- FIM DO PROCESSO: {sent_count} enviados ---\n")
    message_label = (
        f" da mensagem personalizada \"{custom_scenario_name}\""
        if custom_scenario_id and custom_scenario_name
        else ""
    )
    if days_ahead is not None:
        if days_ahead <= 1:
            range_label = " entre os clientes que vencem hoje"
        else:
            window_days = days_ahead - 1
            range_label = (
                f" entre os clientes vencidos há até {window_days} dia{'s' if window_days != 1 else ''} "
                f"e os que vencem nos próximos {window_days} dia{'s' if window_days != 1 else ''}"
            )
    elif date_from or date_to:
        range_label = " no período de vencimento selecionado"
    else:
        range_label = ""
    return {"message": f"Processo finalizado! {sent_count} mensagens enviadas{message_label}{range_label}.", "sent_count": sent_count}


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
    msg, _, media = build_client_reminder_message(client, current_user, days_diff)

    # Definição do canal
    channel = client.notification_channel or "whatsapp"
    success = False
    error_detail = ""

    # --- ENVIO VIA WHATSAPP ---
    if channel == "whatsapp":
        if not current_user.whatsapp_connected:
            raise HTTPException(status_code=400, detail="WhatsApp não conectado. Configure na aba Integração.")

        try:
            success, _, _ = await send_client_reminder(
                current_user,
                client,
                msg,
                media=media,
                telegram_prefix=f"🔔 *Lembrete Manual: {client.name}*",
            )
            if not success:
                error_detail = "A Evolution API retornou erro ou falha no envio."
        except HTTPException:
            raise
        except Exception as e:
            success = False
            error_detail = str(e)

    # --- ENVIO VIA TELEGRAM ---
    elif channel == "telegram":
        if not current_user.telegram_token:
            raise HTTPException(status_code=400, detail="Telegram não configurado.")

        try:
            success, _, _ = await send_client_reminder(
                current_user,
                client,
                msg,
                media=media,
                telegram_prefix=f"🔔 *Lembrete Manual: {client.name}*",
            )
        except HTTPException:
            raise
        except Exception as e:
            success = False
            error_detail = f"Erro Telegram: {str(e)}"

    if success:
        return {"message": f"Mensagem enviada via {channel}!", "sent": True}
    else:
        print(f"❌ Erro no envio manual: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Falha ao enviar mensagem: {error_detail}")