"""
Scraper codificado para Cidade Verde.

Estrutura analisada via chrome-devtools em 2026-05-29:
- Site: estático (sem React/SPA), afiliada SBT Piauí
- Listagem: https://cidadeverde.com/ultimas
  - Links: a[href*="/noticias/"] com padrão /noticias/{id}/{slug}
  - Paginação: /ultimas/p/{N} (padrão numérico simples)
  - Data no card da listagem: span.post-date → "CATEGORIA - DD/MM/YYYY HHhMM"
    → Data disponível SEM entrar no artigo, permite filtro por período na listagem
- Artigo:
  - Sem paywall ✅
  - h1             → título
  - time[datetime] → data ISO 8601 (atributo datetime)
  - .post-body     → corpo do texto
  - meta[og:image] → imagem
  - Autor: não exposto
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from threading import local

from bs4 import BeautifulSoup

from .base import PortalArticle, PortalScraper

_BASE_LISTING = "https://cidadeverde.com/ultimas"
_PAGINATION_TMPL = "https://cidadeverde.com/ultimas/p/{N}"
_ARTICLE_RE = re.compile(r"cidadeverde\.com/noticias/\d+/")

# Regex para extrair data do texto "CATEGORIA - DD/MM/YYYY HHhMM"
_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2})h(\d{2})")


def _parse_listing_date(text: str) -> datetime | None:
    """Parseia 'CATEGORIA - DD/MM/YYYY HHhMM' → datetime UTC."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(3)), int(m.group(2)), int(m.group(1)),
            int(m.group(4)), int(m.group(5)),
            tzinfo=timezone.utc,
        )
    except Exception:
        return None


class CidadeVerdeScraper(PortalScraper):
    name = "Cidade Verde"
    scope = "teresina"
    trust = 4
    description = "Portal afiliado SBT Piauí — cobertura de Teresina e Piauí"
    last_analyzed = "2026-05-29"
    rate_limit = 2.0
    timeout = 30
    pagination_max = 20  # aumentado: data na listagem permite parada precisa

    def __init__(self):
        # Cache de datas extraídas da listagem: url → datetime
        # Populado por fetch_listing_urls(); consultado por extract_date_from_url()
        self._url_dates: dict[str, datetime] = {}

    def extract_date_from_url(self, url: str) -> datetime | None:
        """Retorna data cacheada da listagem — sem precisar baixar o artigo."""
        return self._url_dates.get(url)

    def fetch_listing_urls(self, page: int = 1) -> list[str]:
        """
        Busca a página de listagem e retorna URLs de artigos.
        Também popula self._url_dates com as datas dos cards — permite que
        extract_date_from_url() funcione sem requisição adicional.
        """
        url = _BASE_LISTING if page == 1 else _PAGINATION_TMPL.replace("{N}", str(page))
        html = self._fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []

        for date_span in soup.select(".post-date"):
            date_text = date_span.get_text(strip=True)
            parsed_date = _parse_listing_date(date_text)

            # Sobe na árvore para encontrar o link do artigo no mesmo card
            card = date_span
            for _ in range(6):
                card = card.parent
                if card is None:
                    break
                link = card.find("a", href=_ARTICLE_RE)
                if link:
                    href = link.get("href", "")
                    if href.startswith("/"):
                        href = "https://cidadeverde.com" + href
                    if href and href not in seen and _ARTICLE_RE.search(href):
                        seen.add(href)
                        urls.append(href)
                        if parsed_date:
                            self._url_dates[href] = parsed_date
                    break

        # Fallback: coleta links sem data caso o método acima falhe
        if not urls:
            for a in soup.select('a[href*="/noticias/"]'):
                href = a.get("href", "")
                if href.startswith("/"):
                    href = "https://cidadeverde.com" + href
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

        h1 = soup.select_one("h1")
        art.title = h1.get_text(strip=True) if h1 else None

        # Data preferencial: time[datetime] do artigo; fallback: cache da listagem
        time_el = soup.select_one("time[datetime]")
        if time_el:
            art.date_str = time_el.get("datetime") or time_el.get_text(strip=True)
        elif url in self._url_dates:
            art.date_str = self._url_dates[url].isoformat()

        body_el = soup.select_one(".post-body")
        if body_el:
            seen_p: set[str] = set()
            paras = []
            for p in body_el.select("p"):
                t = p.get_text(separator=" ", strip=True)
                if t and t not in seen_p:
                    seen_p.add(t)
                    paras.append(t)
            art.content = "\n".join(paras) or body_el.get_text(separator="\n", strip=True) or None

        img = soup.select_one('meta[property="og:image"]')
        if img:
            art.image_url = img.get("content")

        art.extraction_quality = self._quality(art)
        return art

    def _quality(self, art: PortalArticle) -> float:
        import re as _re
        if not art.content:
            return 0.0
        words = len(_re.findall(r"\w+", art.content))
        return round(min(min(words / 200.0, 1.0) * 0.6
                         + (0.15 if art.title else 0)
                         + (0.15 if art.date_str else 0), 1.0), 2)
