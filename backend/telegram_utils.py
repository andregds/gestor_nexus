# backend/telegram_utils.py
import httpx


async def send_telegram_message(token: str, chat_id: str, message: str):
    """
    Envia uma mensagem de texto para o Telegram via API oficial.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=10.0)

        if response.status_code != 200:
            # Levanta erro se o Telegram recusar (ex: chat_id errado)
            raise Exception(f"Erro Telegram ({response.status_code}): {response.text}")

        return response.json()