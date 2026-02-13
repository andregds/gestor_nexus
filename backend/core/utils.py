# backend/core/utils.py
from typing import Optional

def generate_reminder_message(client_name: str, days_diff: int) -> Optional[str]:
    """
    Gera a mensagem de lembrete com base na diferença de dias.
    Retorna a mensagem formatada ou None se nenhuma regra for aplicável.
    """
    if days_diff == 0:
        return f"Olá {client_name}! 🚨 Sua assinatura vence HOJE. Renove agora para continuar assistindo."
    elif days_diff == 1:
        return f"Olá {client_name}! ⏰ Sua assinatura vence AMANHÃ. Já realizou a renovação?"
    elif days_diff > 1:
        # Esta mensagem só será usada no envio manual, pois o agendador respeita o 'reminder_days_before'
        return f"Olá {client_name}! 📅 Sua assinatura vence em {days_diff} dias. Evite bloqueios!"
    elif days_diff < 0:
        days_overdue = abs(days_diff)
        return f"Olá {client_name}. ❌ Sua assinatura venceu há {days_overdue} dias. Entre em contato para reativar."

    return None
