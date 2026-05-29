"""
Estratégias de coleta: rss, trafilatura, css_selectors, playwright, portal_list.

portal_list — estratégia para portais com página de listagem + paginação:
  1. Busca a list_url e extrai URLs de artigos via article_link_selector (CSS)
  2. Pagina via pagination_url_pattern (substitui {N})
  3. Para cada URL de artigo, extrai com css_selectors usando os seletores do config
  4. Retorna lista de ExtractionResult via metadata["articles"]
"""
from __future__ import annotations
import time
from typing import Any

from .fetcher import fetch_url
from .extractors import (
    extract_with_trafilatura,
    extract_with_css_selectors,
    extract_with_playwright,
)
from .models import ExtractionResult


def strategy_rss(url: str, config: dict[str, Any] | None = None) -> ExtractionResult:
    """RSS via feedparser — usado apenas para testes unitários de estratégia."""
    result = ExtractionResult(url=url, strategy="rss")
    try:
        import feedparser
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            result.error = f"Feed inválido: {getattr(feed.bozo_exception, '__class__.__name__', 'unknown')}"
            return result
        result.title = feed.feed.get("title")
        result.content = f"{len(feed.entries)} entradas no feed"
        result.extraction_quality = 0.9 if feed.entries else 0.1
    except Exception as exc:
        result.error = str(exc)[:200]
    return result


def strategy_trafilatura(
    url: str,
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 2.0,
) -> ExtractionResult:
    """Baixa HTML e extrai com trafilatura."""
    fetch = fetch_url(url, timeout=timeout, rate_limit=rate_limit)
    if not fetch.ok:
        result = ExtractionResult(url=url, strategy="trafilatura")
        result.error = fetch.error or f"HTTP {fetch.status_code}"
        return result
    return extract_with_trafilatura(fetch.html, url)


def strategy_css_selectors(
    url: str,
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 2.0,
) -> ExtractionResult:
    """Baixa HTML e extrai com seletores CSS do config."""
    cfg = config or {}
    fetch = fetch_url(url, timeout=timeout, rate_limit=rate_limit)
    if not fetch.ok:
        result = ExtractionResult(url=url, strategy="css_selectors")
        result.error = fetch.error or f"HTTP {fetch.status_code}"
        return result
    return extract_with_css_selectors(
        html=fetch.html,
        url=url,
        title_selector=cfg.get("title_selector"),
        content_selector=cfg.get("content_selector"),
        date_selector=cfg.get("date_selector"),
        author_selector=cfg.get("author_selector"),
        image_selector=cfg.get("image_selector"),
    )


def strategy_playwright(
    url: str,
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 5.0,
) -> ExtractionResult:
    """Renderiza com Playwright e extrai com trafilatura."""
    return extract_with_playwright(url, timeout_ms=timeout * 1000)


def strategy_portal_list(
    url: str,
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 2.0,
) -> ExtractionResult:
    """
    Estratégia para portais com página de listagem HTML + paginação.

    config esperado (compatível com source_rules.config_json):
      list_url                  : URL da página de listagem (usa url se não informado)
      article_link_selector     : seletor CSS para <a> de artigos na listagem
      pagination_url_pattern    : padrão com {N} para paginação (ex: ".../pagina-{N}.ghtml")
      pagination_start          : primeira página extra (default 2)
      pagination_max_pages      : quantas páginas extras buscar (default 3)
      title_selector            : seletor do título no artigo
      content_selector          : seletor do corpo no artigo
      date_selector             : seletor da data no artigo
      date_attribute            : atributo a ler da tag de data (ex: "datetime")
      author_selector           : seletor do autor no artigo
      image_selector            : seletor da imagem no artigo
      image_attribute           : atributo a ler da tag de imagem (ex: "content")

    Retorna ExtractionResult com:
      - content = resumo textual (N artigos encontrados, M extraídos)
      - metadata["articles"] = lista de ExtractionResult serializado
      - metadata["urls_found"] = lista de URLs descobertas
    """
    cfg = config or {}
    list_url = cfg.get("list_url") or url
    link_selector = cfg.get("article_link_selector", 'a[href*="/noticia/"][href$=".ghtml"]')
    pagination_pattern = cfg.get("pagination_url_pattern")
    pagination_start = int(cfg.get("pagination_start", 2))
    pagination_max = int(cfg.get("pagination_max_pages", 3))

    result = ExtractionResult(url=list_url, strategy="portal_list")

    # ── 1. Coletar URLs da listagem (página 1 + paginação) ────────────────────
    all_urls: list[str] = []
    seen: set[str] = set()

    def _extract_article_urls(html: str) -> list[str]:
        """Extrai URLs únicas de artigos de um HTML de listagem."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select(link_selector):
            href = a.get("href", "")
            if href and href not in seen:
                seen.add(href)
                urls.append(href)
        return urls

    # Página base
    fetch = fetch_url(list_url, timeout=timeout, rate_limit=0)
    if not fetch.ok:
        result.error = fetch.error or f"HTTP {fetch.status_code} ao buscar listagem"
        return result
    all_urls.extend(_extract_article_urls(fetch.html))

    # Páginas extras (paginação)
    if pagination_pattern:
        for page_n in range(pagination_start, pagination_start + pagination_max):
            page_url = pagination_pattern.replace("{N}", str(page_n))
            time.sleep(rate_limit)
            pf = fetch_url(page_url, timeout=timeout, rate_limit=0)
            if not pf.ok:
                break
            new_urls = _extract_article_urls(pf.html)
            if not new_urls:
                break
            all_urls.extend(new_urls)

    if not all_urls:
        result.error = f"Nenhum artigo encontrado com selector '{link_selector}'"
        return result

    # ── 2. Scraping de cada artigo ────────────────────────────────────────────
    articles = []
    for article_url in all_urls:
        time.sleep(rate_limit)
        art = _scrape_article(article_url, cfg, timeout)
        articles.append({
            "url": art.url,
            "ok": art.ok,
            "title": art.title,
            "content_length": len(art.content or ""),
            "date": art.date_str,
            "author": art.author,
            "image": art.image_url,
            "quality": art.extraction_quality,
            "quality_label": art.quality_label(),
            "error": art.error,
        })

    ok_count = sum(1 for a in articles if a["ok"])
    result.content = f"{len(all_urls)} URLs encontradas, {ok_count} extraídas com sucesso"
    result.extraction_quality = round(ok_count / len(all_urls), 2) if all_urls else 0.0
    result.metadata = {
        "articles": articles,
        "urls_found": all_urls,
        "total_urls": len(all_urls),
        "ok_count": ok_count,
    }
    return result


def _scrape_article(
    url: str,
    cfg: dict[str, Any],
    timeout: int,
) -> ExtractionResult:
    """Baixa e extrai um artigo usando os seletores do config."""
    fetch = fetch_url(url, timeout=timeout, rate_limit=0)
    if not fetch.ok:
        r = ExtractionResult(url=url, strategy="css_selectors")
        r.error = fetch.error or f"HTTP {fetch.status_code}"
        return r

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(fetch.html, "html.parser")
    r = ExtractionResult(url=url, strategy="css_selectors")

    # Título
    if cfg.get("title_selector"):
        el = soup.select_one(cfg["title_selector"])
        r.title = el.get_text(strip=True) if el else None

    # Corpo
    if cfg.get("content_selector"):
        els = soup.select(cfg["content_selector"])
        if els:
            r.content = "\n".join(e.get_text(separator="\n", strip=True) for e in els) or None

    # Data
    if cfg.get("date_selector"):
        el = soup.select_one(cfg["date_selector"])
        if el:
            attr = cfg.get("date_attribute", "datetime")
            r.date_str = el.get(attr) or el.get_text(strip=True) or None

    # Autor
    if cfg.get("author_selector"):
        el = soup.select_one(cfg["author_selector"])
        r.author = el.get_text(strip=True) if el else None

    # Imagem
    if cfg.get("image_selector"):
        el = soup.select_one(cfg["image_selector"])
        if el:
            attr = cfg.get("image_attribute", "src")
            r.image_url = el.get(attr) or el.get("src") or None

    # Qualidade
    from .extractors import _quality_score
    r.extraction_quality = _quality_score(r)
    return r
