"""
Interface base para scrapers específicos de portal.

Cada portal tem seu próprio arquivo em portals/ com código dedicado.
NÃO usar config JSON para definir seletores — isso vai aqui, no código.

Por que código e não config?
- Estrutura de portal muda → código vai no git, revisado, testado
- Cada portal tem quirks próprios (dedup, paginação, limpeza de texto)
- Config JSON não consegue expressar lógica condicional
"""
from __future__ import annotations
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..fetcher import fetch_url
from ..models import ExtractionResult


@dataclass
class PortalArticle:
    """Artigo extraído por um scraper de portal."""
    url: str
    title: str | None = None
    content: str | None = None
    author: str | None = None
    date_str: str | None = None
    image_url: str | None = None
    extraction_quality: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.content)


@dataclass
class PortalScrapeResult:
    """Resultado de um scrape completo de portal."""
    portal_name: str
    urls_found: list[str] = field(default_factory=list)   # novas, extraídas
    urls_skipped: list[str] = field(default_factory=list)  # já conhecidas, puladas
    urls_out_of_range: list[str] = field(default_factory=list)  # fora do período
    articles: list[PortalArticle] = field(default_factory=list)
    pages_fetched: int = 0
    stopped_by_date: bool = False  # paginação parou por artigos antigos demais
    error: str | None = None

    @property
    def ok_count(self) -> int:
        return sum(1 for a in self.articles if a.ok)

    @property
    def ok(self) -> bool:
        return self.error is None

    def summary(self) -> str:
        parts = []
        total_seen = len(self.urls_found) + len(self.urls_skipped) + len(self.urls_out_of_range)
        parts.append(f"{total_seen} URLs vistas")
        if self.urls_out_of_range:
            parts.append(f"{len(self.urls_out_of_range)} fora do período")
        if self.urls_skipped:
            parts.append(f"{len(self.urls_skipped)} já conhecidas")
        parts.append(f"{len(self.urls_found)} novas")
        if self.articles:
            parts.append(f"{self.ok_count}/{len(self.articles)} extraídas")
        if self.stopped_by_date:
            parts.append("parou por data")
        return " · ".join(parts)


class PortalScraper(ABC):
    """
    Classe base para scrapers específicos de portal.

    Subclasses devem implementar:
    - fetch_listing_urls(page) → list[str]
    - scrape_article(url) → PortalArticle

    Opcionalmente sobrescrever:
    - extract_date_from_url(url) → datetime | None
      Quando o portal inclui a data na URL (ex: /2026/05/29/), permite
      filtrar por período ANTES de baixar o artigo — evita requisições desnecessárias.
    """

    name: str = ""
    scope: str = "brasil"
    trust: int = 3
    description: str = ""
    last_analyzed: str = ""
    rate_limit: float = 2.0
    timeout: int = 30
    pagination_max: int = 10  # aumentado — scraping por período precisa de mais páginas

    @abstractmethod
    def fetch_listing_urls(self, page: int = 1) -> list[str]:
        """Retorna URLs de artigos da página N da listagem."""
        ...

    @abstractmethod
    def scrape_article(self, url: str) -> PortalArticle:
        """Baixa e extrai um artigo completo."""
        ...

    def extract_date_from_url(self, url: str) -> datetime | None:
        """
        Extrai data da URL sem precisar baixar o artigo.
        Override em subclasses quando o portal inclui data na URL.
        Ex: /2026/5/29/ → datetime(2026, 5, 29)
        """
        return None

    def scrape(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        max_articles: int = 500,
        max_pages: int | None = None,
        dry_run: bool = False,
        skip_known: bool = True,
        source_id: int | None = None,
    ) -> PortalScrapeResult:
        """
        Scraping por período: extrai artigos entre since e until.

        Lógica de parada inteligente:
        - Portais com data na URL: filtra antes de baixar o artigo
        - Para de paginar quando encontra artigos mais velhos que since
        - skip_known pula URLs já em scraped_pages / articles
        """
        result = PortalScrapeResult(portal_name=self.name)
        n_pages = max_pages or self.pagination_max
        seen: set[str] = set()

        # Normaliza datas para UTC
        since_utc = _to_utc(since)
        until_utc = _to_utc(until)

        # Carrega URLs já conhecidas do banco uma única vez
        known_urls: set[str] = set()
        if skip_known:
            try:
                from ..runs import get_known_urls
                known_urls = get_known_urls(source_id)
            except Exception:
                pass

        try:
            for page in range(1, n_pages + 1):
                try:
                    page_urls = self.fetch_listing_urls(page=page)
                except Exception as exc:
                    result.error = f"Erro na listagem p{page}: {str(exc)[:200]}"
                    break

                if not page_urls:
                    break

                page_had_valid = False
                page_all_old = True  # presume que a página é toda antiga até provar o contrário

                page_hit_floor = False  # encontrou artigo mais velho que since

                for url in page_urls:
                    if url in seen:
                        continue
                    seen.add(url)

                    url_date = self.extract_date_from_url(url)

                    if url_date is not None:
                        # Portal com data na URL: filtra antes de baixar
                        if until_utc and url_date > until_utc:
                            result.urls_out_of_range.append(url)
                            continue  # mais recente — pula, mas NÃO para a paginação
                        if since_utc and url_date < since_utc:
                            result.urls_out_of_range.append(url)
                            page_hit_floor = True  # artigos ficando antigos demais
                            continue
                    # Sem data na URL ou dentro do período: inclui

                    if url in known_urls:
                        result.urls_skipped.append(url)
                    else:
                        result.urls_found.append(url)

                result.pages_fetched = page

                # Só para quando encontra artigos MAIS VELHOS que since (floor)
                # Não para quando encontra artigos mais recentes que until (ceiling)
                if since_utc and page_hit_floor:
                    result.stopped_by_date = True
                    break

                if len(result.urls_found) >= max_articles:
                    break

                if page < n_pages:
                    time.sleep(self.rate_limit)

            if dry_run:
                return result

            for url in result.urls_found[:max_articles]:
                # Rate limit garantido na base — subclasses não precisam implementar
                time.sleep(max(self.rate_limit, 0.5))
                try:
                    article = self.scrape_article(url)

                    # Verifica data do artigo após extração (portais sem data na URL)
                    if article.date_str:
                        art_date = _parse_article_date(article.date_str)
                        if art_date:
                            if since_utc and art_date < since_utc:
                                result.urls_out_of_range.append(url)
                                continue
                            if until_utc and art_date > until_utc:
                                result.urls_out_of_range.append(url)
                                continue

                except Exception as exc:
                    article = PortalArticle(url=url, error=str(exc)[:200])
                result.articles.append(article)

        except Exception as exc:
            result.error = str(exc)[:300]

        return result

    def _fetch(self, url: str) -> str | None:
        fetch = fetch_url(url, timeout=self.timeout, rate_limit=0)
        return fetch.html if fetch.ok else None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scope": self.scope,
            "trust": self.trust,
            "description": self.description,
            "last_analyzed": self.last_analyzed,
            "rate_limit": self.rate_limit,
            "pagination_max": self.pagination_max,
        }


# ── helpers ────────────────────────────────────────────────────────────────────

def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_article_date(date_str: str) -> datetime | None:
    """Tenta parsear data de um artigo a partir de string comum."""
    if not date_str:
        return None
    # ISO 8601
    try:
        from dateutil import parser as dp
        return _to_utc(dp.parse(date_str))
    except Exception:
        pass
    # DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", date_str)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                            tzinfo=timezone.utc)
        except Exception:
            pass
    return None
