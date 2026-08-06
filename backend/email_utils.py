import smtplib
from email.message import EmailMessage
from typing import Any, Dict

EMAIL_PROVIDER_PRESETS = {
    "gmail": {"smtp_host": "smtp.gmail.com", "smtp_port": "587", "smtp_security": "tls"},
    "hotmail": {"smtp_host": "smtp.office365.com", "smtp_port": "587", "smtp_security": "tls"},
    "outlook": {"smtp_host": "smtp.office365.com", "smtp_port": "587", "smtp_security": "tls"},
    "yahoo": {"smtp_host": "smtp.mail.yahoo.com", "smtp_port": "587", "smtp_security": "tls"},
}

DEFAULT_EMAIL_SETTINGS = {
    "provider": "gmail",
    "enabled": False,
    "sender_name": "Gestor Nexus",
    "sender_email": "",
    "username": "",
    "password": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_security": "tls",
}

GMAIL_BAD_CREDENTIALS_MESSAGE = (
    "Gmail recusou o usuário ou senha. Para resolver: selecione Gmail, informe o Gmail completo "
    "em E-mail remetente e Usuário SMTP, ative a verificação em duas etapas na Conta Google e use "
    "uma Senha de app do Google no campo Senha. A senha normal da conta geralmente não funciona "
    "no SMTP do Gmail."
)

EMAIL_REMINDERS_DISABLED_MESSAGE = (
    "E-mail desativado para lembretes. Vá em Comunicação > E-mail de lembretes, "
    "preencha os dados SMTP, marque Ativar envio por e-mail e clique em Salvar E-mail."
)


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def normalize_email_settings(value: Any, user=None) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    normalized = DEFAULT_EMAIL_SETTINGS.copy()
    normalized.update({key: source.get(key, normalized[key]) for key in normalized})

    provider = _safe_str(normalized.get("provider")) or "gmail"
    normalized["provider"] = provider

    preset = EMAIL_PROVIDER_PRESETS.get(provider)
    if preset:
        normalized["smtp_host"] = preset["smtp_host"]
        normalized["smtp_port"] = preset["smtp_port"]
        normalized["smtp_security"] = preset["smtp_security"]

    normalized["enabled"] = bool(normalized.get("enabled"))
    normalized["sender_name"] = _safe_str(normalized.get("sender_name")) or "Gestor Nexus"
    normalized["sender_email"] = _safe_str(normalized.get("sender_email")).lower()
    normalized["username"] = _safe_str(normalized.get("username"))
    normalized["smtp_host"] = _safe_str(normalized.get("smtp_host"))
    normalized["smtp_port"] = _safe_str(normalized.get("smtp_port")) or "587"
    normalized["smtp_security"] = _safe_str(normalized.get("smtp_security")) or "tls"
    return normalized


def get_user_email_settings(user) -> Dict[str, Any]:
    settings = getattr(user, "payment_api_settings", None)
    settings = settings if isinstance(settings, dict) else {}
    return normalize_email_settings(settings.get("email_settings"), user)


def set_user_email_settings(user, email_settings: Dict[str, Any]) -> Dict[str, Any]:
    settings = getattr(user, "payment_api_settings", None)
    settings = settings.copy() if isinstance(settings, dict) else {}
    settings["email_settings"] = normalize_email_settings(email_settings, user)
    user.payment_api_settings = settings
    return settings


def send_email_message(user, recipient_email: str, subject: str, body: str, require_enabled: bool = True):
    email_settings = get_user_email_settings(user)
    if require_enabled and not email_settings.get("enabled"):
        raise RuntimeError(EMAIL_REMINDERS_DISABLED_MESSAGE)

    recipient = _safe_str(recipient_email).lower()
    if not recipient or "@" not in recipient:
        raise RuntimeError("Cliente sem e-mail válido.")

    sender_email = email_settings.get("sender_email") or email_settings.get("username")
    username = email_settings.get("username") or sender_email
    password = email_settings.get("password")
    smtp_host = email_settings.get("smtp_host")
    smtp_port = int(email_settings.get("smtp_port") or 587)
    security = email_settings.get("smtp_security")

    if not sender_email or not username or not password or not smtp_host:
        raise RuntimeError("Configuração SMTP incompleta. Vá em Comunicação > E-mail de lembretes, preencha remetente, usuário SMTP, senha, servidor e salve novamente.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{email_settings.get('sender_name')} <{sender_email}>"
    message["To"] = recipient
    message.set_content(body)

    try:
        if security == "ssl":
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                server.login(username, password)
                server.send_message(message)
            return

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if security == "tls":
                server.starttls()
            server.login(username, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        provider = email_settings.get("provider")
        error_text = str(exc).lower()
        if provider == "gmail" or "gmail" in smtp_host.lower() or "badcredentials" in error_text:
            raise RuntimeError(GMAIL_BAD_CREDENTIALS_MESSAGE) from exc
        raise RuntimeError("Usuário ou senha SMTP não aceitos. Confira o e-mail, usuário SMTP, senha e provedor selecionado.") from exc
