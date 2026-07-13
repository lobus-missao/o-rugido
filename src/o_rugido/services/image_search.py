"""Busca de imagens via SearXNG.

Substitui o Serper.dev. SearXNG agrega Google/Bing/DDG Images.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from o_rugido.core.config import SEARXNG_URL

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8
_DEFAULT_LIMIT = 12

# Dominios que bloqueiam crawler anonimo (403/404 mesmo com User-Agent
# comum). Filtrar antes de tentar baixar economiza tempo e evita cards
# faltando imagem quando so o Nº 1 do resultado era bloqueado.
_BLOCKED_HOST_SUFFIXES = (
    "lookaside.instagram.com",
    "cdninstagram.com",
    "fbcdn.net",
    "fbsbx.com",
    "instagram.com",
)


def is_blocked_image_url(url: str) -> bool:
    """True se o dominio da URL bloqueia crawler anonimo."""
    if not url:
        return True
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return True
    return any(host == suffix or host.endswith("." + suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def search_images(
    query: str,
    limit: int = _DEFAULT_LIMIT,
    *,
    engines: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []

    params: dict[str, Any] = {
        "q": query,
        "categories": "images",
        "format": "json",
        "safesearch": 0,
        "language": "pt-BR",
    }
    if engines:
        params["engines"] = engines

    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params=params,
            timeout=timeout,
            headers={"User-Agent": "o-rugido/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        _logger.warning("searxng falhou: %s", exc)
        return []
    except ValueError as exc:
        _logger.warning("searxng resposta nao-json: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    skipped_blocked = 0
    for item in data.get("results", []):
        img = item.get("img_src") or item.get("thumbnail_src")
        if not img:
            continue
        if is_blocked_image_url(img):
            skipped_blocked += 1
            continue
        out.append({
            "url": img,
            "thumbnail": item.get("thumbnail_src") or img,
            "source": item.get("url"),
            "title": (item.get("title") or "").strip(),
            "engine": item.get("engine"),
        })
        if len(out) >= limit:
            break

    if skipped_blocked:
        _logger.info("searxng: %d imagem(ns) bloqueada(s) filtrada(s)", skipped_blocked)
    return out


def first_image_url(query: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str | None:
    results = search_images(query, limit=1, timeout=timeout)
    return results[0]["url"] if results else None
