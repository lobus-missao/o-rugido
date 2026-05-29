"""Extratores de conteúdo: trafilatura e css_selectors."""
from __future__ import annotations
import re

from .models import ExtractionResult

# ── trafilatura ────────────────────────────────────────────────────────────────

def extract_with_trafilatura(html: str, url: str) -> ExtractionResult:
    """Extrai título + texto principal via trafilatura."""
    result = ExtractionResult(url=url, strategy="trafilatura")
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        metadata = trafilatura.extract_metadata(html, default_url=url)

        result.content = text or None
        if metadata:
            result.title = metadata.title or None
            result.author = metadata.author or None
            result.date_str = str(metadata.date) if metadata.date else None
            result.image_url = metadata.image or None

        result.extraction_quality = _quality_score(result)

    except ImportError:
        result.error = "trafilatura não instalado — execute: pip install trafilatura"
    except Exception as exc:
        result.error = f"Erro de extração: {str(exc)[:200]}"

    return result


# ── CSS Selectors ──────────────────────────────────────────────────────────────

def extract_with_css_selectors(
    html: str,
    url: str,
    title_selector: str | None = None,
    content_selector: str | None = None,
    date_selector: str | None = None,
    author_selector: str | None = None,
    image_selector: str | None = None,
) -> ExtractionResult:
    """Extrai campos usando seletores CSS (BeautifulSoup)."""
    result = ExtractionResult(url=url, strategy="css_selectors")
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        if title_selector:
            tag = soup.select_one(title_selector)
            result.title = tag.get_text(strip=True) if tag else None

        if content_selector:
            tags = soup.select(content_selector)
            result.content = "\n".join(t.get_text(separator="\n", strip=True) for t in tags) or None

        if date_selector:
            tag = soup.select_one(date_selector)
            if tag:
                result.date_str = tag.get("datetime") or tag.get_text(strip=True) or None

        if author_selector:
            tag = soup.select_one(author_selector)
            result.author = tag.get_text(strip=True) if tag else None

        if image_selector:
            tag = soup.select_one(image_selector)
            if tag:
                result.image_url = tag.get("src") or tag.get("data-src") or None

        if not any([title_selector, content_selector, date_selector, author_selector]):
            result.error = "Nenhum seletor configurado"
        else:
            result.extraction_quality = _quality_score(result)

    except Exception as exc:
        result.error = f"Erro de extração CSS: {str(exc)[:200]}"

    return result


# ── playwright ─────────────────────────────────────────────────────────────────

def extract_with_playwright(url: str, timeout_ms: int = 30_000) -> ExtractionResult:
    """Renderiza página via Playwright e depois extrai com trafilatura."""
    result = ExtractionResult(url=url, strategy="playwright")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": "NewsRadarRSS/1.0 (editorial bot)"})
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                html = page.content()
            except PWTimeout:
                result.error = f"Timeout Playwright após {timeout_ms}ms"
                return result
            finally:
                browser.close()

        # Após renderizar, extrai com trafilatura
        traf = extract_with_trafilatura(html, url)
        result.content = traf.content
        result.title = traf.title
        result.author = traf.author
        result.date_str = traf.date_str
        result.image_url = traf.image_url
        result.extraction_quality = traf.extraction_quality
        result.error = traf.error

    except ImportError:
        result.error = "Playwright não instalado — execute: playwright install chromium"
    except Exception as exc:
        result.error = f"Erro Playwright: {str(exc)[:300]}"

    return result


# ── helpers ────────────────────────────────────────────────────────────────────

def _quality_score(result: ExtractionResult) -> float:
    """Pontuação simples 0.0–1.0 baseada em campos preenchidos e tamanho do texto."""
    if not result.content:
        return 0.0
    words = len(re.findall(r"\w+", result.content))
    # >200 palavras = boa qualidade base
    text_score = min(words / 200.0, 1.0) * 0.6
    field_score = sum([
        0.15 if result.title else 0,
        0.15 if result.date_str else 0,
        0.10 if result.author else 0,
    ])
    return round(min(text_score + field_score, 1.0), 2)
