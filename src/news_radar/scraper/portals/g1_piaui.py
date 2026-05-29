"""
Scraper codificado para G1 Piauí.

Estrutura analisada via chrome-devtools em 2026-05-29:
- Listagem: https://g1.globo.com/pi/piaui/cidade/teresina/
  - SSR puro (sem React/SPA)
  - Links de artigos: a[href*="/noticia/"][href$=".ghtml"]
  - Paginação: .../index/feed/pagina-{N}.ghtml
    Obs: páginas 1-3 já vêm inline; o "mostrar mais" aponta para página 4.
         Para iterar corretamente começamos da página 1 e incrementamos.

- Artigo: https://g1.globo.com/pi/piaui/noticia/YYYY/MM/DD/slug.ghtml
  - Sem paywall ✅
  - h1                                    → título
  - .content-text                         → corpo (limpo, sem anúncios)
  - time[datetime]  attr=datetime         → data ISO 8601
  - .content-publication-data__from       → autor ("Por Nome, g1 PI")
  - meta[property="og:image"]  attr=content → imagem principal

Atualizar last_analyzed e seletores sempre que a estrutura mudar.
"""
from __future__ import annotations
import re

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..extractors import _quality_score
from ..models import ExtractionResult
from .base import PortalArticle, PortalScraper

_BASE_LISTING = "https://g1.globo.com/pi/piaui/cidade/teresina/"
_PAGINATION_TMPL = "https://g1.globo.com/pi/piaui/cidade/teresina/index/feed/pagina-{N}.ghtml"
_ARTICLE_LINK_RE = re.compile(r"https://g1\.globo\.com/pi/piaui/noticia/\d{4}/\d{2}/\d{2}/[^\"']+\.ghtml")


class G1PiauiScraper(PortalScraper):
    name = "G1 Piauí"
    scope = "piaui"
    trust = 5
    description = "Cobertura do G1 Globo para Piauí e Teresina"
    last_analyzed = "2026-05-29"
    rate_limit = 2.0
    timeout = 30
    pagination_max = 3

    def extract_date_from_url(self, url: str) -> datetime | None:
        # URL: /noticia/2026/5/29/slug.ghtml
        m = re.search(r"/noticia/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                tzinfo=timezone.utc)
            except Exception:
                pass
        return None

    def fetch_listing_urls(self, page: int = 1) -> list[str]:
        """Retorna URLs de artigos da página N da listagem."""
        if page == 1:
            url = _BASE_LISTING
        else:
            url = _PAGINATION_TMPL.replace("{N}", str(page))

        html = self._fetch(url)
        if html is None:
            return []

        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []
        for a in soup.select('a[href*="/noticia/"][href$=".ghtml"]'):
            href = a.get("href", "")
            # Normaliza URLs relativas
            if href.startswith("/"):
                href = "https://g1.globo.com" + href
            if href and href not in seen and _ARTICLE_LINK_RE.match(href):
                seen.add(href)
                urls.append(href)
        return urls

    def scrape_article(self, url: str) -> PortalArticle:
        """Extrai um artigo completo do G1 Piauí."""
        html = self._fetch(url)
        if html is None:
            return PortalArticle(url=url, error="Falha ao baixar página")

        soup = BeautifulSoup(html, "html.parser")
        article = PortalArticle(url=url)

        # Título
        h1 = soup.select_one("h1")
        article.title = h1.get_text(strip=True) if h1 else None

        # Corpo — parágrafos dentro de .content-text (evita duplicar o container)
        content_els = soup.select(".content-text p")
        if not content_els:
            # fallback: texto direto do container
            content_els = soup.select(".content-text")
        if content_els:
            seen_p: set[str] = set()
            paragraphs = []
            for el in content_els:
                t = el.get_text(separator=" ", strip=True)
                if t and t not in seen_p:
                    seen_p.add(t)
                    paragraphs.append(t)
            article.content = "\n".join(paragraphs) or None

        # Data ISO 8601
        time_el = soup.select_one("time[datetime]")
        if time_el:
            article.date_str = time_el.get("datetime") or time_el.get_text(strip=True)

        # Autor — remove o prefixo "Por " (incluindo espaços não-quebráveis)
        author_el = soup.select_one(".content-publication-data__from")
        if author_el:
            raw = author_el.get_text(separator=" ", strip=True)
            article.author = re.sub(r"\s+", " ", re.sub(r"^Por[\s\xa0]+", "", raw, flags=re.IGNORECASE)).strip()

        # Imagem principal (og:image)
        img_el = soup.select_one('meta[property="og:image"]')
        if img_el:
            article.image_url = img_el.get("content")

        # Qualidade simples baseada em tamanho do texto
        if article.content:
            words = len(re.findall(r"\w+", article.content))
            text_score = min(words / 200.0, 1.0) * 0.6
            field_score = (
                (0.15 if article.title else 0)
                + (0.15 if article.date_str else 0)
                + (0.10 if article.author else 0)
            )
            article.extraction_quality = round(min(text_score + field_score, 1.0), 2)

        return article
