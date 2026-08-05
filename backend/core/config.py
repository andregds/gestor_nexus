# backend/core/config.py (apenas a parte relevante para referência)
import os
from pathlib import Path

from dotenv import load_dotenv
from core.runtime_env import get_runtime_env


BASE_DIR = Path(__file__).resolve().parents[2]
DOTENV_PATH = BASE_DIR / ".env"


def load_project_env():
    load_dotenv(DOTENV_PATH)


def _normalize_env_value(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def get_evolution_api_url():
    load_project_env()
    value = _normalize_env_value(get_runtime_env("EVOLUTION_API_URL"))
    if value:
        return value.rstrip("/")
    return None


def get_evolution_api_key():
    load_project_env()
    return _normalize_env_value(get_runtime_env("EVOLUTION_API_KEY"))


def get_whatsapp_api_provider():
    load_project_env()
    value = _normalize_env_value(get_runtime_env("WHATSAPP_API_PROVIDER"))
    if value:
        return value.lower()
    if get_waha_api_url() and get_waha_api_key():
        return "waha"
    return "evolution"


def get_waha_api_url():
    load_project_env()
    value = _normalize_env_value(get_runtime_env("WAHA_API_URL"))
    if value:
        return value.rstrip("/")
    return None


def get_waha_api_key():
    load_project_env()
    return _normalize_env_value(get_runtime_env("WAHA_API_KEY"))


def get_public_backend_url():
    load_project_env()
    value = (
        _normalize_env_value(get_runtime_env("EVOLUTION_WEBHOOK_BASE_URL"))
        or _normalize_env_value(get_runtime_env("BACKEND_PUBLIC_URL"))
        or _normalize_env_value(get_runtime_env("APP_PUBLIC_URL"))
        or _normalize_env_value(get_runtime_env("PUBLIC_BASE_URL"))
    )
    if value:
        return value.rstrip("/")
    return None


load_project_env()

EVOLUTION_API_URL = get_evolution_api_url()
EVOLUTION_API_KEY = get_evolution_api_key()
WHATSAPP_API_PROVIDER = get_whatsapp_api_provider()
WAHA_API_URL = get_waha_api_url()
WAHA_API_KEY = get_waha_api_key()

if WHATSAPP_API_PROVIDER == "waha" and (not WAHA_API_URL or not WAHA_API_KEY):
    print(
        "AVISO: WAHA_API_URL ou WAHA_API_KEY nao configuradas "
        f"nas variaveis de ambiente do sistema/registro ou em {DOTENV_PATH}"
    )
elif WHATSAPP_API_PROVIDER != "waha" and (not EVOLUTION_API_URL or not EVOLUTION_API_KEY):
    print(
        "AVISO: EVOLUTION_API_URL ou EVOLUTION_API_KEY nao configuradas "
        f"nas variaveis de ambiente do sistema/registro ou em {DOTENV_PATH}"
    )

# Outras configurações globais podem vir aqui
