"""Alertas via Telegram Bot API para bots de capital real.

Setup (usuario):
  1. Fale com @BotFather no Telegram, /newbot, copie o token -> TELEGRAM_BOT_TOKEN.
  2. Fale com o bot recem-criado (qualquer mensagem), depois acesse
     https://api.telegram.org/bot<TOKEN>/getUpdates e pegue "chat":{"id": ...} -> TELEGRAM_CHAT_ID.
  3. Preencha ambos no .env.

Se as vars nao estiverem setadas, send_telegram() apenas loga localmente (nao quebra o bot).
"""
import json
import os
import urllib.request

from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def send_telegram(text, disable_notification=False):
    """Envia uma mensagem de texto simples. Retorna True se enviado, False caso contrario
    (inclusive quando as credenciais nao estao configuradas -- fail-safe, nunca lanca excecao
    para nao derrubar o loop de trading por causa de um alerta)."""
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[telegram_disabled] {text}", flush=True)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": CHAT_ID,
        "text": text[:4000],
        "disable_notification": disable_notification,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as exc:
        print(f"[telegram_error] {exc}", flush=True)
        return False


if __name__ == "__main__":
    ok = send_telegram("\U0001F7E2 Teste de alerta Telegram -- trading-engine")
    print("enviado=", ok)
