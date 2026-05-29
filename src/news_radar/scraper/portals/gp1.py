"""
Scraper codificado para GP1.

Estrutura analisada via chrome-devtools em 2026-05-29:
- Site: estático
- Listagem: https://www.gp1.com.br/piaui/
  - Links de artigos via h2 a, h3 a, h4 a sem query string
  - URL pattern: gp1.com.br/{section}/noticia/YYYY/M/DD/{slug}-{id}.html
  - Paginação: não detectada — carrega ~18 artigos por página
- Artigo:
  - Sem paywall ✅
  - h1                → título
  - .article-texto    → corpo (div com parágrafos limpos)
  - time              → data (texto: "DD/MM/YYYY HHhMM", primeiro elemento)
  - meta[og:image]    → imagem
  - Autor: não exposto
"""
from __future__ import annotations
import re

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .base import PortalArticle, PortalScraper

_BASE_LISTING = "https://www.gp1.com.br/piaui/"
_ARTICLE_RE = re.compile(r"gp1\.com\.br/.+/noticia/.+\.html$")
_DATE_RE = re.compile(r"\d{1,2}/\d{2}/\d{4}")


class GP1Scraper(PortalScraper):
    name = "GP1"
    scope = "piaui"
    trust = 4
    description = "Primeiro Grande Portal de Notícias do Piauí"
    last_analyzed = "2026-05-29"
    rate_limit = 2.0
    timeout = 30
    pagination_max = 1  # sem paginação detectada na listagem

    def extract_date_from_url(self, url: str) -> datetime | None:
        # URL: /noticia/2026/5/29/slug-624098.html
        m = re.search(r"/noticia/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                tzinfo=timezone.utc)
            except Exception:
                pass
        return None

    def fetch_listing_urls(self, page: int = 1) -> list[str]:
        if page > 1:
            return []  # paginação não detectada
        html = self._fetch(_BASE_LISTING)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []
        for a in soup.select("h2 a[href], h3 a[href], h4 a[href]"):
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://www.gp1.com.br" + href
            # Só links diretos de notícia (sem query string, sem redes sociais)
            if (href and "?" not in href and href not in seen
                    and _ARTICLE_RE.search(href)):
                seen.add(href)
                urls.append(href)
        return urls

    def scrape_article(self, url: str) -> PortalArticle:
        html = self._fetch(url)
        if not html:
            return PortalArticle(url=url, error="Falha ao baixar página")

        soup = BeautifulSoup(html, "html.parser")
        art = PortalArticle(url=url)

        h1 = soup.select_one("h1")
        art.title = h1.get_text(strip=True) if h1 else None

        # Data — primeiro <time> com texto de data
        for time_el in soup.select("time"):
            text = time_el.get_text(strip=True)
            if _DATE_RE.search(text):
                art.date_str = text
                break

        # Corpo — .article-texto
        body_el = soup.select_one(".article-texto")
        if body_el:
            seen_p: set[str] = set()
            paras = []
            for p in body_el.select("p"):
                t = p.get_text(separator=" ", strip=True)
                if t and t not in seen_p and len(t) > 20:
                    seen_p.add(t)
                    paras.append(t)
            art.content = "\n".join(paras) or None

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
