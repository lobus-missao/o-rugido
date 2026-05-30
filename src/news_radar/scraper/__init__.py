"""
Pacote de scraping da Fase 10.1/10.2 — coexiste com o pipeline RSS existente.

Duas frentes distintas:
  - Estratégias genéricas (trafilatura, css_selectors): configuração por fonte
  - Portais codificados (scraper/portals/): código dedicado por portal

Fase 10.2 adiciona o pipeline de ingestão: scraped_pages → articles.
"""
from .jobs import run_extraction_test, run_source_scrape
from .rules import list_source_rules, get_source_rule, upsert_source_rule
from .runs import create_scrape_run, finish_scrape_run, list_scrape_runs
from .portals import PORTAL_SCRAPERS
from .ingestion import (
    ingest_scraped_pages,
    build_article_from_scraped_page,
    get_eligible_pages,
    count_eligible_pages,
    mark_scraped_page_ingested,
    mark_scraped_page_ingestion_error,
)

__all__ = [
    "run_extraction_test",
    "run_source_scrape",
    "list_source_rules",
    "get_source_rule",
    "upsert_source_rule",
    "create_scrape_run",
    "finish_scrape_run",
    "list_scrape_runs",
    "PORTAL_SCRAPERS",
    "ingest_scraped_pages",
    "build_article_from_scraped_page",
    "get_eligible_pages",
    "count_eligible_pages",
    "mark_scraped_page_ingested",
    "mark_scraped_page_ingestion_error",
]
