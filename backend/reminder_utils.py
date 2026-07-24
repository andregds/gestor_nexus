import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from telegram_utils import send_telegram_message
from whatsapp_utils import send_whatsapp_notification


DEFAULT_REMINDER_TEMPLATES = {
    "upcoming": "Olá {nome_cliente}! 📅 Sua assinatura vence em {dias_restantes} dias, no dia {data_vencimento}. Evite bloqueios e garanta a renovação a tempo.",
    "tomorrow": "Olá {nome_cliente}! ⏰ Sua assinatura vence amanhã ({data_vencimento}). Se precisar renovar, responda esta mensagem.",
    "today": "Olá {nome_cliente}! 🚨 Sua assinatura vence hoje ({data_vencimento}). Renove agora para continuar com o acesso ativo.",
    "overdue": "Olá {nome_cliente}. ❌ Sua assinatura venceu há {dias_atraso} dias, em {data_vencimento}. Entre em contato para reativar o acesso.",
    "fallback": "Olá {nome_cliente}! 📌 Lembrete: sua assinatura está ativa e vence no dia {data_vencimento}.",
}

EMPTY_REMINDER_MEDIA = {
    "data_url": "",
    "file_name": "",
    "mime_type": "",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_media(value: Any) -> Dict[str, str]:
    source = _safe_dict(value)
    data_url = str(source.get("data_url") or "").strip()
    mime_type = str(source.get("mime_type") or "").strip()
    file_name = str(source.get("file_name") or "").strip()

    if data_url.startswith("data:") and ";base64," in data_url and not mime_type:
        header_body = data_url[5:data_url.index(",")]
        mime_type = header_body.split(";", 1)[0]

    return {
        "data_url": data_url,
        "mime_type": mime_type,
        "file_name": file_name,
    }


def _slugify_scenario_id(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _safe_str(value))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return normalized


def _normalize_template_entry(value: Any, fallback_template: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        template = _safe_str(value.get("template")) or fallback_template
        media = _normalize_media(value.get("media"))
    else:
        template = _safe_str(value) or fallback_template
        media = _normalize_media(None)
    return {
        "template": template,
        "media": media,
    }


def normalize_reminder_templates(value: Any) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    source = _safe_dict(value)

    for key, default_value in DEFAULT_REMINDER_TEMPLATES.items():
        normalized[key] = _normalize_template_entry(source.get(key), default_value)

    return normalized


def normalize_custom_reminder_scenarios(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        items = [
            {"name": scenario_name, "template": scenario_template}
            for scenario_name, scenario_template in value.items()
        ]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []

    normalized: List[Dict[str, Any]] = []
    used_ids = set(DEFAULT_REMINDER_TEMPLATES.keys())

    for index, item in enumerate(items, start=1):
        source = _safe_dict(item)
        name = _safe_str(source.get("name"))
        template = _safe_str(source.get("template"))
        media = _normalize_media(source.get("media"))
        scenario_id = _slugify_scenario_id(source.get("id"))

        if not name and not template:
            continue

        if not name:
            name = f"Mensagem {index}"

        base_id = scenario_id or f"custom-{_slugify_scenario_id(name) or 'cenario'}"
        candidate_id = base_id
        suffix = 2

        while not candidate_id or candidate_id in used_ids:
            candidate_id = f"{base_id}-{suffix}"
            suffix += 1

        used_ids.add(candidate_id)
        normalized.append(
            {
                "id": candidate_id,
                "name": name,
                "template": template,
                "media": media,
            }
        )

    return normalized


def normalize_reminder_media(value: Any) -> Dict[str, str]:
    return _normalize_media(value)


def get_user_reminder_templates(user) -> Dict[str, Dict[str, Any]]:
    settings = _safe_dict(getattr(user, "payment_api_settings", None))
    return normalize_reminder_templates(settings.get("reminder_templates"))


def get_user_reminder_scenarios(user) -> List[Dict[str, Any]]:
    settings = _safe_dict(getattr(user, "payment_api_settings", None))
    return normalize_custom_reminder_scenarios(settings.get("reminder_scenarios"))


def get_user_reminder_media(user) -> Dict[str, str]:
    settings = _safe_dict(getattr(user, "payment_api_settings", None))
    return normalize_reminder_media(settings.get("reminder_media"))


def set_user_reminder_settings(
    user,
    reminder_templates: Optional[Dict[str, Any]] = None,
    reminder_scenarios: Optional[List[Dict[str, Any]]] = None,
    reminder_media: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = _safe_dict(getattr(user, "payment_api_settings", None)).copy()

    if reminder_templates is not None:
        settings["reminder_templates"] = normalize_reminder_templates(reminder_templates)
    else:
        settings["reminder_templates"] = normalize_reminder_templates(settings.get("reminder_templates"))

    if reminder_scenarios is not None:
        settings["reminder_scenarios"] = normalize_custom_reminder_scenarios(reminder_scenarios)
    else:
        settings["reminder_scenarios"] = normalize_custom_reminder_scenarios(settings.get("reminder_scenarios"))

    if reminder_media is not None:
        settings["reminder_media"] = normalize_reminder_media(reminder_media)
    else:
        settings["reminder_media"] = normalize_reminder_media(settings.get("reminder_media"))

    user.payment_api_settings = settings
    return settings


def format_expiration_date(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return ""


def build_reminder_context(client, user, days_diff: int) -> Dict[str, str]:
    expiration_date = format_expiration_date(getattr(client, "expiration_date", None))
    client_name = str(getattr(client, "name", "") or "").strip()
    client_login = str(getattr(client, "login", "") or "").strip()
    server_name = str(getattr(client, "server_name", "") or "").strip()
    whatsapp = str(getattr(client, "whatsapp", "") or "").strip()
    days_left = str(max(days_diff, 0))
    days_overdue = str(abs(days_diff)) if days_diff < 0 else "0"
    owner_name = str(getattr(user, "name", "") or "").strip()

    return {
        "nome_cliente": client_name,
        "data_vencimento": expiration_date,
        "dias_restantes": days_left,
        "dias_atraso": days_overdue,
        "login_cliente": client_login,
        "nome_servidor": server_name,
        "whatsapp_cliente": whatsapp,
        "nome_responsavel": owner_name,
        # Compatibilidade com placeholders legados em inglês.
        "client_name": client_name,
        "expiration_date": expiration_date,
        "days_left": days_left,
        "days_overdue": days_overdue,
        "login": client_login,
        "server_name": server_name,
        "whatsapp": whatsapp,
        "owner_name": owner_name,
    }


def select_template_key(days_diff: int) -> str:
    if days_diff < 0:
        return "overdue"
    if days_diff == 0:
        return "today"
    if days_diff == 1:
        return "tomorrow"
    if days_diff > 1:
        return "upcoming"
    return "fallback"


def render_reminder_template(template: str, context: Dict[str, str]) -> str:
    rendered = str(template or "").strip()
    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", str(value or ""))
    return rendered


def build_client_reminder_message(client, user, days_diff: int) -> Tuple[str, str, Dict[str, str]]:
    templates = get_user_reminder_templates(user)
    template_key = select_template_key(days_diff)
    template_entry = templates.get(template_key) or templates.get("fallback") or _normalize_template_entry(None, DEFAULT_REMINDER_TEMPLATES["fallback"])
    context = build_reminder_context(client, user, days_diff)
    media = _normalize_media(template_entry.get("media"))
    return render_reminder_template(template_entry.get("template"), context), template_key, media


def build_client_custom_reminder_message(client, user, days_diff: int, scenario_id: str) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    scenario_key = _safe_str(scenario_id)
    scenarios = get_user_reminder_scenarios(user)
    scenario = next((item for item in scenarios if _safe_str(item.get("id")) == scenario_key), None)

    if not scenario:
        raise ValueError("Mensagem personalizada não encontrada.")

    template = _safe_str(scenario.get("template"))
    if not template:
        raise ValueError("A mensagem personalizada selecionada está vazia.")

    context = build_reminder_context(client, user, days_diff)
    return render_reminder_template(template, context), scenario, _normalize_media(scenario.get("media"))


async def send_client_reminder(user, client, message: str, telegram_prefix: Optional[str] = None, media: Optional[Dict[str, Any]] = None):
    channel = getattr(client, "notification_channel", None) or "whatsapp"

    if channel == "whatsapp":
        if not getattr(user, "whatsapp_connected", False):
            raise RuntimeError("WhatsApp não conectado. Configure na aba Integração.")

        success = await send_whatsapp_notification(
            number=getattr(client, "whatsapp", ""),
            message=message,
            instance_name=getattr(user, "whatsapp_instance", None),
            media=media if media and media.get("data_url") else None,
        )

        if not success:
            return False, channel, "A Evolution API retornou erro ou falha no envio."
        return True, channel, ""

    if channel == "telegram":
        if not getattr(user, "telegram_token", None) or not getattr(user, "telegram_chat_id", None):
            raise RuntimeError("Telegram não configurado.")

        body = message
        if telegram_prefix:
            body = f"{telegram_prefix}\n\n{message}"

        await send_telegram_message(
            token=user.telegram_token,
            chat_id=user.telegram_chat_id,
            message=body,
        )
        return True, channel, ""

    raise RuntimeError(f"Canal de notificação não suportado: {channel}")
