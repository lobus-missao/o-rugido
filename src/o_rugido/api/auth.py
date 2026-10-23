"""Autenticação server-to-server da API (n8n -> API).

Rotas de automação exigem o header ``X-Internal-Key`` quando a env
``INTERNAL_API_KEY`` está definida. Sem a env, a API mantém o comportamento
anterior (aberta) e loga um aviso — permite subir o código antes de o n8n
passar a enviar o header.

Ficam públicas, de propósito:
- ``/health``: healthcheck do container.
- ``/cards/<arquivo>.png``: o Instagram baixa o card por aqui.
- ``/edit``: o editor abre o link do Telegram; já é protegido por token próprio.
- ``/api/image-search``: chamada pelo navegador na própria página ``/edit``.
"""
from __future__ import annotations

import hmac
import logging
import os

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

HEADER = "X-Internal-Key"

PUBLIC_ENDPOINTS = frozenset({
    "health.health",
    "render.serve_card",
    "edit.edit_dispatch",
    "images.image_search",
})

_warned_open = False


def _configured_key() -> str:
    return os.environ.get("INTERNAL_API_KEY", "")


def _check_internal_key():
    global _warned_open

    # Rota inexistente ou pública: segue o fluxo normal (404 / handler).
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None

    expected = _configured_key()
    if not expected:
        if not _warned_open:
            logger.warning(
                "INTERNAL_API_KEY nao definida: rotas de automacao da API estao SEM autenticacao"
            )
            _warned_open = True
        return None

    provided = request.headers.get(HEADER, "")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


def init_auth(app: Flask) -> None:
    app.before_request(_check_internal_key)
