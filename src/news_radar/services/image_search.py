"""Busca de imagens via SearXNG.

Substitui o Serper.dev. SearXNG agrega Google/Bing/DDG Images.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from news_radar.core.config import SEARXNG_URL

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8
_DEFAULT_LIMIT = 12


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
            headers={"User-Agent": "news-radar/1.0"},
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
    for item in data.get("results", []):
        img = item.get("img_src") or item.get("thumbnail_src")
        if not img:
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

    return out


def first_image_url(query: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str | None:
    results = search_images(query, limit=1, timeout=timeout)
    return results[0]["url"] if results else None
