from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _api(method: str, **kwargs) -> dict[str, Any]:
    r = requests.post(f"{API}/{method}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def send_card_for_approval(article: dict[str, Any], card_path: str | Path) -> dict[str, Any]:
    """Envia o card PNG para o Telegram com botões de aprovação/rejeição."""
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID precisam estar configurados no .env")

    card_path = Path(card_path)
    if not card_path.exists():
        raise FileNotFoundError(f"Card não encontrado: {card_path}")

    article_id = article.get("id", "")
    title = (article.get("title") or "")[:80]
    priority = (article.get("priority") or "-").upper()
    editoria = article.get("category") or "-"
    score = float(article.get("final_score_brasil") or article.get("final_score_piaui") or 0)

    caption = (
        f"*{priority}* | {editoria}\n"
        f"{title}\n"
        f"Score: {score:.0f}"
    )

    inline_keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar", "callback_data": f"approve:{article_id}"},
            {"text": "❌ Rejeitar", "callback_data": f"reject:{article_id}"},
        ]]
    }

    with open(card_path, "rb") as photo:
        result = _api(
            "sendPhoto",
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(inline_keyboard, ensure_ascii=False),
            },
            files={"photo": photo},
        )

    return result


def set_webhook(webhook_url: str) -> dict[str, Any]:
    """Registra o webhook do Telegram apontando para o n8n."""
    return _api("setWebhook", json={"url": webhook_url})


def delete_webhook() -> dict[str, Any]:
    return _api("deleteWebhook")


def get_webhook_info() -> dict[str, Any]:
    return _api("getWebhookInfo")
