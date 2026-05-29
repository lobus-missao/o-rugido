"""
Configurações descobertas via inspeção real dos portais (devtools).
Cada entrada é um dict compatível com source_rules.config_json.

Atualizar sempre que a estrutura do portal mudar.
Versão: 2026-05-29
"""
from __future__ import annotations

# ── G1 Piauí ──────────────────────────────────────────────────────────────────
# Analisado em 2026-05-29 via chrome-devtools
# SSR puro, sem React/SPA, sem paywall
G1_PIAUI_CONFIG = {
    "strategy": "portal_list",
    "list_url": "https://g1.globo.com/pi/piaui/cidade/teresina/",
    # Seletor CSS para extrair URLs de artigos da listagem
    "article_link_selector": 'a[href*="/noticia/"][href$=".ghtml"]',
    # Padrão de paginação — {N} substituído pelo número da página
    "pagination_url_pattern": "https://g1.globo.com/pi/piaui/cidade/teresina/index/feed/pagina-{N}.ghtml",
    "pagination_start": 2,
    "pagination_max_pages": 5,
    # Seletores dentro da página de artigo
    "title_selector": "h1",
    "content_selector": ".content-text",
    "date_selector": "time[datetime]",
    "date_attribute": "datetime",
    "author_selector": ".content-publication-data__from",
    "image_selector": 'meta[property="og:image"]',
    "image_attribute": "content",
    # Metadados
    "notes": "SSR, sem paywall. Seletores validados em 2026-05-29.",
    "requires_js": False,
}

# ── G1 Piauí (editoria geral) ─────────────────────────────────────────────────
G1_PIAUI_GERAL_CONFIG = {
    **G1_PIAUI_CONFIG,
    "list_url": "https://g1.globo.com/pi/piaui/",
    "pagination_url_pattern": "https://g1.globo.com/pi/piaui/index/feed/pagina-{N}.ghtml",
}

# Índice de configs por nome de source
PORTAL_CONFIGS: dict[str, dict] = {
    "G1 Piauí": G1_PIAUI_CONFIG,
    "G1 Teresina": G1_PIAUI_CONFIG,  # mesma estrutura
}
