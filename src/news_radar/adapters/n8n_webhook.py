from __future__ import annotations

import logging
from typing import Any

import requests

from news_radar.core.config import N8N_WEBHOOK_URL

_logger = logging.getLogger(__name__)


def notify_ingestion_complete(summary: dict[str, Any], timeout: int = 5) -> bool:
    if not N8N_WEBHOOK_URL:
        return False
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={"event": "ingestion.complete", "summary": summary},
            timeout=timeout,
        )
        if response.status_code >= 400:
            _logger.warning("webhook n8n %s: %s", response.status_code, response.text[:200])
            return False
        return True
    except requests.RequestException as exc:
        _logger.warning("falha webhook n8n: %s", str(exc)[:200])
        return False
