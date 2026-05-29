"""
Scrapers codificados por portal.

Cada portal tem seu arquivo próprio. Para adicionar um novo portal:
1. Criar portals/nome_do_portal.py com classe que herda PortalScraper
2. Registrar em PORTAL_SCRAPERS abaixo

NÃO adicionar portais via config JSON ou interface — o código é a documentação.

Status por portal (atualizar ao analisar novos):
  G1 Piauí      ✅ 2026-05-29 — SSR, css selectors
  Cidade Verde  ✅ 2026-05-29 — SSR, .post-body
  GP1           ✅ 2026-05-29 — SSR, .article-texto
  Portal O Dia  ✅ 2026-05-29 — Tailwind, .text-content
  180graus      ❌ Cloudflare bloqueia — aguarda solução
  MeioNews      🔲 WordPress — a analisar
  Viagora       🔲 a analisar
"""
from __future__ import annotations

from .base import PortalArticle, PortalScrapeResult, PortalScraper
from .g1_piaui import G1PiauiScraper
from .cidade_verde import CidadeVerdeScraper
from .gp1 import GP1Scraper
from .portal_odia import PortalODiaScraper

# Registro central: nome → instância do scraper
PORTAL_SCRAPERS: dict[str, PortalScraper] = {
    "G1 Piauí": G1PiauiScraper(),
    "Cidade Verde": CidadeVerdeScraper(),
    "GP1": GP1Scraper(),
    "Portal O Dia": PortalODiaScraper(),
}

__all__ = [
    "PortalScraper",
    "PortalArticle",
    "PortalScrapeResult",
    "PORTAL_SCRAPERS",
    "G1PiauiScraper",
    "CidadeVerdeScraper",
    "GP1Scraper",
    "PortalODiaScraper",
]
