"""
Telegram poller — processa callbacks de aprovação editorial em 2 etapas.
Artigo → Card. Uso: python scripts/telegram_poller.py
"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import os, requests
from news_radar.repositories.articles import update_card_status
from news_radar.services.editorial import (
    handle_callback_action,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"
offset = 0

print("Telegram poller — aprovação em 2 etapas (artigo → card)")
print("Aguardando callbacks... (Ctrl+C para parar)\n")

while True:
    try:
        r = requests.get(f"{API}/getUpdates",
                         params={"offset": offset, "timeout": 30}, timeout=35)
        for update in r.json().get("result", []):
            offset = update["update_id"] + 1
            cb = update.get("callback_query")
            if not cb or ":" not in cb.get("data", ""):
                continue

            action, payload = cb["data"].split(":", 1)
            user = cb.get("from", {}).get("first_name", "Editor")

            requests.post(f"{API}/answerCallbackQuery",
                          json={"callback_query_id": cb["id"], "text": "✓"})

            if action in {"dispatch_approve", "dispatch_reject", "card_approve", "card_reject", "card_regenerate"}:
                result = handle_callback_action(action, payload, user)
                print(f"{action} · dispatch {payload} · por {user} · {result.get('status', result.get('error', 'ok'))}")

            elif action == "approve":  # legado
                update_card_status(payload, status="approved")
                requests.post(f"{API}/editMessageCaption", json={
                    "chat_id": cb["message"]["chat"]["id"],
                    "message_id": cb["message"]["message_id"],
                    "caption": f"✅ APROVADO por {user}",
                    "reply_markup": {"inline_keyboard": []},
                })
                print(f"✅ Card legado aprovado · {payload[:12]}...")

            elif action == "reject":  # legado
                update_card_status(payload, status="rejected")
                requests.post(f"{API}/editMessageCaption", json={
                    "chat_id": cb["message"]["chat"]["id"],
                    "message_id": cb["message"]["message_id"],
                    "caption": f"❌ REJEITADO por {user}",
                    "reply_markup": {"inline_keyboard": []},
                })
                print(f"❌ Card legado rejeitado · {payload[:12]}...")

    except KeyboardInterrupt:
        print("\nPoller encerrado.")
        break
    except Exception as e:
        print(f"Erro: {e}")
        time.sleep(5)
