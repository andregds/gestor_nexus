# backend/core/config.py (apenas a parte relevante para referência)
import os
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")

if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
    print("⚠️ AVISO: EVOLUTION_API_URL ou EVOLUTION_API_KEY não configuradas no .env")

# Outras configurações globais podem vir aqui
