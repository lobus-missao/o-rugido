"""
Scraper codificado para Portal O Dia.

Estrutura analisada via chrome-devtools em 2026-05-29:
- Site: Tailwind CSS + HTML estático (sem React SPA)
- Listagem: https://portalodia.com/
  - Links de artigos: a[href*="/noticias/"][href$=".html"]
  - URL pattern: portalodia.com/noticias/{section}/{slug}-{id}.html
  - Paginação: não detectada na home (artigos recentes apenas)
- Artigo:
  - Sem paywall ✅
  - meta[og:title]     → título (h1 vazia por CSS — título está no og:title)
  - .text-content      → corpo principal
  - data via texto "Publicada em DD/MM/YYYY às HHhMM" dentro de .grid
  - meta[og:image]     → imagem
  - Autor: não exposto
"""
from __future__ import annotations
import re

from bs4 import BeautifulSoup

from .base import PortalArticle, PortalScraper

_BASE_LISTING = "https://portalodia.com/"
_ARTICLE_RE = re.compile(r"portalodia\.com/noticias/.+\.html$")
_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+às\s+(\d{2}h\d{2})")


class PortalODiaScraper(PortalScraper):
    name = "Portal O Dia"
    scope = "piaui"
    trust = 4
    description = "Jornal O Dia — Piauí e Teresina, com versão digital"
    last_analyzed = "2026-05-29"
    rate_limit = 2.0
    timeout = 30
    pagination_max = 1  # home carrega artigos recentes; sem paginação detectada

    def fetch_listing_urls(self, page: int = 1) -> list[str]:
        if page > 1:
            return []
        html = self._fetch(_BASE_LISTING)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []
        for a in soup.select('a[href*="/noticias/"]'):
            href = a.get("href", "")
            if not href.endswith(".html"):
                continue
            if href.startswith("/"):
                href = "https://portalodia.com" + href
            if href and href not in seen and _ARTICLE_RE.search(href):
                seen.add(href)
                urls.append(href)
        return urls

    def scrape_article(self, url: str) -> PortalArticle:
        html = self._fetch(url)
        if not html:
            return PortalArticle(url=url, error="Falha ao baixar página")

        soup = BeautifulSoup(html, "html.parser")
        art = PortalArticle(url=url)

        # Título via og:title (h1 está vazia por CSS)
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title:
            raw = og_title.get("content", "")
            # Remove sufixo " - Portal O Dia"
            art.title = re.sub(r"\s*-\s*Portal O Dia\s*$", "", raw, flags=re.IGNORECASE).strip()
        else:
            h1 = soup.select_one("h1")
            art.title = h1.get_text(strip=True) if h1 else None

        # Corpo — .text-content
        body_el = soup.select_one(".text-content")
        if body_el:
            seen_p: set[str] = set()
            paras = []
            for p in body_el.select("p"):
                t = p.get_text(separator=" ", strip=True)
                if t and t not in seen_p and len(t) > 20:
                    seen_p.add(t)
                    paras.append(t)
            art.content = "\n".join(paras) or body_el.get_text(separator="\n", strip=True) or None

        # Data — texto "Publicada em DD/MM/YYYY às HHhMM"
        full_text = soup.get_text(" ")
        m = _DATE_RE.search(full_text)
        if m:
            art.date_str = f"{m.group(1)} {m.group(2)}"

        img = soup.select_one('meta[property="og:image"]')
        if img:
            art.image_url = img.get("content")

        art.extraction_quality = self._quality(art)
        return art

    def _quality(self, art: PortalArticle) -> float:
        if not art.content:
            return 0.0
        words = len(re.findall(r"\w+", art.content))
        return round(min(min(words / 200.0, 1.0) * 0.6
                         + (0.15 if art.title else 0)
                         + (0.15 if art.date_str else 0), 1.0), 2)
