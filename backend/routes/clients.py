# backend/routes/clients.py
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
import asyncio

# --- IMPORTS DE DEPENDÊNCIAS ---
from core.dependencies import get_db, get_current_user
from models import User, Client
from reminder_utils import (
    build_client_custom_reminder_message,
    build_client_reminder_message,
    clear_client_reminder_error,
    normalize_reminder_error_message,
    send_client_reminder,
    set_client_reminder_error,
)
from email_utils import EMAIL_REMINDERS_DISABLED_MESSAGE

router = APIRouter(prefix="/clients", tags=["Clientes"])


# --- SCHEMAS ---

class ClientCreate(BaseModel):
    name: str
    login: str
    email: Optional[str] = None
    server_name: Optional[str] = None
    plan_price: Optional[float] = None
    selected_products: Optional[List[Dict[str, Any]]] = None
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
    email: Optional[str] = None
    server_name: Optional[str] = None
    plan_price: Optional[float] = None
    selected_products: Optional[List[Dict[str, Any]]] = None
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
    reminder_error_message: Optional[str] = None
    reminder_error_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BulkReminderRequest(BaseModel):
    client_ids: Optional[List[int]] = None


def resolve_days_window(days_ahead: int, today: date) -> tuple[date, date]:
    offset = max(days_ahead - 1, 0)
    return today - timedelta(days=offset), today + timedelta(days=offset)


def mark_user_last_reminder_run(db: Session, user_id: int):
    user_db = db.query(User).filter(User.id == user_id).first()
    if not user_db:
        return
    user_db.last_reminder_run_at = datetime.now()
    db.commit()


def normalize_selected_products(selected_products: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not selected_products:
        return []

    normalized_products: List[Dict[str, Any]] = []

    for item in selected_products:
        if not isinstance(item, dict):
            continue

        product_name = str(item.get("name", "") or "").strip()
        product_id_value = item.get("product_id")
        price_value = item.get("price")

        if not product_name:
            continue

        try:
            product_price = float(price_value)
        except (TypeError, ValueError):
            continue

        if product_price < 0:
            continue

        product_id = None
        if product_id_value not in (None, ""):
            try:
                product_id = int(product_id_value)
            except (TypeError, ValueError):
                product_id = None

        normalized_products.append(
            {
                "product_id": product_id,
                "name": product_name,
                "price": round(product_price, 2),
            }
        )

    return normalized_products


# ==========================================
# ROTAS ESPECIAIS (DEVEM VIR ANTES DO CRUD)
# ==========================================

@router.post("/process-now")
async def process_reminders_now(
        filter_type: Optional[str] = "default",  # Recebe o filtro do Frontend
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        days_ahead: Optional[int] = None,
        payload: Optional[BulkReminderRequest] = Body(None),
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

    filtered_client_ids = payload.client_ids if payload and payload.client_ids is not None else None
    using_explicit_client_filter = filtered_client_ids is not None

    clients_query = db.query(Client).filter(Client.owner_id == current_user.id)
    if using_explicit_client_filter:
        unique_client_ids = list(dict.fromkeys(filtered_client_ids))
        invalid_client_ids = [client_id for client_id in unique_client_ids if not isinstance(client_id, int) or client_id <= 0]
        if invalid_client_ids:
            raise HTTPException(status_code=400, detail="Lista de clientes filtrados inválida.")

        clients = clients_query.filter(Client.id.in_(unique_client_ids)).all() if unique_client_ids else []
        found_ids = {client.id for client in clients}
        missing_ids = [client_id for client_id in unique_client_ids if client_id not in found_ids]
        if missing_ids:
            raise HTTPException(status_code=400, detail="Um ou mais clientes filtrados não foram encontrados.")
    else:
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
    if using_explicit_client_filter:
        print(f"🎯 Envio restrito aos IDs filtrados no frontend: {filtered_client_ids}")
    print(f"👥 Total de Clientes Analisados: {len(clients)}")

    if using_explicit_client_filter and not clients:
        mark_user_last_reminder_run(db, current_user.id)
        return {
            "message": "Processo finalizado! Nenhum cliente filtrado para envio.",
            "sent_count": 0,
        }

    # Verifica conexão
    has_whatsapp = current_user.whatsapp_connected
    has_telegram = bool(current_user.telegram_token)
    has_email = bool((current_user.payment_api_settings or {}).get("email_settings", {}).get("enabled"))

    if not has_whatsapp and not has_telegram and not has_email:
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
        if using_explicit_client_filter and filter_type == "default":
            should_send = True

        # 1. Filtro: Vencidos (expired)
        elif filter_type == "expired":
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
                    msg, scenario_data, media = build_client_custom_reminder_message(client, current_user, days_diff, custom_scenario_id)
                else:
                    msg, template_key, media = build_client_reminder_message(client, current_user, days_diff)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            # --- ENVIO ---
            channel = client.notification_channel or "whatsapp"
            success = False
            error_detail = ""

            # Envio WhatsApp
            if channel == "whatsapp" and has_whatsapp:
                try:
                    success, _, error_detail = await send_client_reminder(
                        current_user,
                        client,
                        msg,
                        media=media,
                        telegram_prefix=f"🔔 *Cobrança Manual em Massa: {client.name}*",
                    )
                    if success:
                        print(f"   -> WhatsApp enviado com sucesso!")
                    else:
                        print(f"   -> Falha no envio do WhatsApp: {error_detail or 'API retornou erro.'}")
                except Exception as e:
                    print(f"   -> Erro técnico no WhatsApp: {e}")
                    success = False
                    error_detail = normalize_reminder_error_message(e)

            # Envio Telegram
            elif channel == "telegram" and has_telegram:
                try:
                    success, _, error_detail = await send_client_reminder(
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
                    error_detail = normalize_reminder_error_message(e)

            elif channel == "email" and has_email:
                try:
                    success, _, error_detail = await send_client_reminder(
                        current_user,
                        client,
                        msg,
                        media=media,
                        telegram_prefix=f"🔔 *Cobrança Manual em Massa: {client.name}*",
                    )
                    print(f"   -> E-mail enviado com sucesso!")
                except Exception as e:
                    print(f"   -> Erro técnico no E-mail: {e}")
                    success = False
                    error_detail = normalize_reminder_error_message(e)

            elif channel == "email":
                error_detail = EMAIL_REMINDERS_DISABLED_MESSAGE

            if success:
                if clear_client_reminder_error(client):
                    db.commit()
                sent_count += 1
                await asyncio.sleep(1)  # Delay para evitar bloqueio
            else:
                if set_client_reminder_error(client, error_detail or f"Falha ao enviar via {channel}."):
                    db.commit()
  
    print(f"--- FIM DO PROCESSO: {sent_count} enviados ---\n")
    mark_user_last_reminder_run(db, current_user.id)
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
    elif using_explicit_client_filter:
        range_label = " entre os clientes filtrados"
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
    payload = client_data.dict()
    payload["selected_products"] = normalize_selected_products(payload.get("selected_products"))
    new_client = Client(
        **payload,
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
    if "selected_products" in update_data:
        update_data["selected_products"] = normalize_selected_products(update_data.get("selected_products"))
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
    msg, template_key, media = build_client_reminder_message(client, current_user, days_diff)

    # Definição do canal
    channel = client.notification_channel or "whatsapp"
    success = False
    error_detail = ""

    # --- ENVIO VIA WHATSAPP ---
    if channel == "whatsapp":
        if not current_user.whatsapp_connected:
            raise HTTPException(status_code=400, detail="WhatsApp não conectado. Configure na aba Comunicação.")

        try:
            success, _, error_detail = await send_client_reminder(
                current_user,
                client,
                msg,
                media=media,
                telegram_prefix=f"🔔 *Lembrete Manual: {client.name}*",
            )
            if not success:
                error_detail = error_detail or "A WAHA retornou erro ou falha no envio."
        except HTTPException as exc:
            error_detail = normalize_reminder_error_message(exc)
            if set_client_reminder_error(client, error_detail):
                db.commit()
            raise
        except Exception as e:
            success = False
            error_detail = normalize_reminder_error_message(e)

    # --- ENVIO VIA TELEGRAM ---
    elif channel == "telegram":
        if not current_user.telegram_token:
            raise HTTPException(status_code=400, detail="Telegram não configurado.")

        try:
            success, _, error_detail = await send_client_reminder(
                current_user,
                client,
                msg,
                media=media,
                telegram_prefix=f"🔔 *Lembrete Manual: {client.name}*",
            )
        except HTTPException as exc:
            error_detail = normalize_reminder_error_message(exc)
            if set_client_reminder_error(client, error_detail):
                db.commit()
            raise
        except Exception as e:
            success = False
            error_detail = normalize_reminder_error_message(e)

    elif channel == "email":
        try:
            success, _, error_detail = await send_client_reminder(
                current_user,
                client,
                msg,
                media=media,
                telegram_prefix=f"🔔 *Lembrete Manual: {client.name}*",
            )
        except HTTPException as exc:
            error_detail = normalize_reminder_error_message(exc)
            if set_client_reminder_error(client, error_detail):
                db.commit()
            raise
        except Exception as e:
            success = False
            error_detail = normalize_reminder_error_message(e)

    if success:
        if clear_client_reminder_error(client):
            db.commit()
        mark_user_last_reminder_run(db, current_user.id)
        if error_detail:
            return {"message": error_detail, "sent": True, "delivery_confirmed": False}
        return {"message": f"Mensagem entregue via {channel}!", "sent": True, "delivery_confirmed": True}
    else:
        if set_client_reminder_error(client, error_detail or f"Falha ao enviar via {channel}."):
            db.commit()
        mark_user_last_reminder_run(db, current_user.id)
        print(f"❌ Erro no envio manual: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Falha ao enviar mensagem: {error_detail}")