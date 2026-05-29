"""Mapeia nome de estratégia para função executora."""
from __future__ import annotations
from typing import Any, Callable

from .models import ExtractionResult
from .strategies import (
    strategy_rss,
    strategy_trafilatura,
    strategy_css_selectors,
    strategy_playwright,
    strategy_portal_list,
)

STRATEGY_REGISTRY: dict[str, Callable[..., ExtractionResult]] = {
    "rss": strategy_rss,
    "trafilatura": strategy_trafilatura,
    "css_selectors": strategy_css_selectors,
    "playwright": strategy_playwright,
    "portal_list": strategy_portal_list,
}

STRATEGY_LABELS = {
    "rss": "RSS (feedparser)",
    "trafilatura": "Trafilatura (HTML estático)",
    "css_selectors": "CSS Selectors (estruturado)",
    "playwright": "Playwright (JS pesado)",
    "portal_list": "Portal List (listagem + paginação)",
}


def get_strategy(name: str) -> Callable[..., ExtractionResult] | None:
    return STRATEGY_REGISTRY.get(name)


def run_strategy(
    strategy: str,
    url: str,
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 2.0,
) -> ExtractionResult:
    """Executa a estratégia indicada. Retorna erro amigável se desconhecida."""
    fn = get_strategy(strategy)
    if fn is None:
        from .models import ExtractionResult
        res = ExtractionResult(url=url, strategy=strategy)
        res.error = f"Estratégia desconhecida: '{strategy}'. Disponíveis: {list(STRATEGY_REGISTRY)}"
        return res
    return fn(url=url, config=config, timeout=timeout, rate_limit=rate_limit)
