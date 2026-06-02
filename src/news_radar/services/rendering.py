from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from news_radar.core.config import CARDS_DIR, TEMPLATES_DIR, ensure_dirs

from ..repositories.articles import articles_pending_card, update_card_status

logger = logging.getLogger(__name__)

_PRIORITY_LABEL: dict[str, str] = {
    "critica": "CRITICA",
    "alta": "ALTA",
    "media": "MEDIA",
    "baixa": "BAIXA",
    "ruido": "RUIDO",
}
_PRIORITY_COLOR: dict[str, str] = {
    "critica": "#dc2626",
    "alta": "#ea580c",
    "media": "#d97706",
    "baixa": "#16a34a",
    "ruido": "#6b7280",
}


def build_card_context(
    article: dict[str, Any],
    scope: str | None = None,
    title_override: str | None = None,
    subtitle_override: str | None = None,
    image_url: str | None = None,
) -> dict[str, str]:
    """Build the full template variable dict from an article.

    Supports all placeholders used by card.html and card-editorial-base.html.
    Every value is a plain string — never None, never a raw '{{...}}' marker.
    title_override / subtitle_override take priority over ai_json suggestions.
    """
    ai_json = article.get("ai_json") or {}
    if isinstance(ai_json, str):
        try:
            ai_json = json.loads(ai_json)
        except Exception:
            ai_json = {}

    # ── Título ─────────────────────────────────────────────────────────────────
    titulo = (
        title_override
        or ai_json.get("titulo_sugerido")
        or article.get("title")
        or ""
    ).strip()

    # ── Subtítulo (card-editorial-base.html) ───────────────────────────────────
    subtitulo_raw = (subtitle_override or ai_json.get("subtitulo_sugerido") or "").strip()
    subtitulo_html = (
        f'<div class="card-subtitulo">{subtitulo_raw}</div>' if subtitulo_raw else ""
    )

    # ── Prioridade ─────────────────────────────────────────────────────────────
    priority = (article.get("priority") or "").lower()
    priority_label = _PRIORITY_LABEL.get(priority, priority.upper() or "?")
    priority_color = _PRIORITY_COLOR.get(priority, "#6b7280")

    # ── Editoria / Categoria ───────────────────────────────────────────────────
    category = article.get("category") or ai_json.get("editoria") or "-"
    categoria_tag = (
        f'<span class="tag tag-categoria">{category}</span>'
        if category and category != "-"
        else ""
    )

    # ── Pontos-chave ───────────────────────────────────────────────────────────
    pontos_chave_raw = ai_json.get("pontos_chave") or []
    if isinstance(pontos_chave_raw, str):
        pontos_chave_raw = [pontos_chave_raw]
    pontos_li = "".join(f"<li>{p}</li>" for p in pontos_chave_raw[:4])
    # card.html uses {{pontos_chave}} inside an existing <ul>
    # card-editorial-base.html uses {{pontos_html}} as a standalone block
    pontos_html_block = (
        f'<div class="card-pontos"><ul>{pontos_li}</ul></div>' if pontos_li else ""
    )

    # ── Resumo ─────────────────────────────────────────────────────────────────
    resumo = (ai_json.get("resumo_curto") or article.get("summary") or "")[:200]

    # ── Score ──────────────────────────────────────────────────────────────────
    score = float(article.get("final_score_piaui") or 0)

    # ── IA badge ───────────────────────────────────────────────────────────────
    ia_badge = "IA" if article.get("ai_score") else "AUTO"

    # ── Localidade ─────────────────────────────────────────────────────────────
    localidade = ai_json.get("localidade") or article.get("locality") or ""
    localidade_tag = (
        f'<span class="tag local">{localidade}</span>' if localidade else ""
    )

    # ── Entidades (máx 3) ──────────────────────────────────────────────────────
    entidades = ai_json.get("entidades") or []
    if isinstance(entidades, str):
        try:
            entidades = json.loads(entidades)
        except Exception:
            entidades = [entidades]
    entidades_tags = "".join(
        f'<span class="tag entidade">{e}</span>' for e in entidades[:3]
    )

    # ── Riqueza de conteúdo (card.html legacy) ─────────────────────────────────
    summary_len = len(article.get("summary") or "")
    if summary_len >= 500:
        conteudo_tag = f'<span class="tag conteudo-rico">Conteudo rico ({summary_len} chars)</span>'
    elif summary_len >= 200:
        conteudo_tag = f'<span class="tag conteudo-medio">Conteudo medio ({summary_len} chars)</span>'
    elif summary_len >= 50:
        conteudo_tag = f'<span class="tag conteudo-simples">Conteudo simples ({summary_len} chars)</span>'
    else:
        conteudo_tag = '<span class="tag conteudo-simples">Sem resumo</span>'

    # ── Justificativa do score ─────────────────────────────────────────────────
    justif = ai_json.get("justificativa_score") or ""
    justificativa_html = (
        f'<div class="justificativa">{justif[:140]}</div>' if justif else ""
    )

    hero_url = (image_url or "").strip()
    hero_empty_class = "" if hero_url else " empty"

    return {
        "titulo": titulo,
        "subtitulo_html": subtitulo_html,
        "editoria": category,
        "prioridade": priority_label,
        "prioridade_cor": priority_color,
        "resumo": resumo,
        "pontos_chave": pontos_li,
        "pontos_html": pontos_html_block,
        "fonte": article.get("source") or "",
        "data": str(article.get("published_at") or "")[:10],
        "score": f"{score:.0f}",
        "ia_badge": ia_badge,
        "localidade_tag": localidade_tag,
        "entidades_tags": entidades_tags,
        "categoria_tag": categoria_tag,
        "conteudo_tag": conteudo_tag,
        "justificativa_html": justificativa_html,
        "url": article.get("url") or article.get("canonical_url") or "",
        "image_url": hero_url,
        "hero_empty_class": hero_empty_class,
    }


def _render_html(
    article: dict[str, Any],
    template: str,
    scope: str | None = None,
    title_override: str | None = None,
    subtitle_override: str | None = None,
    image_url: str | None = None,
) -> str:
    """Substitute all {{placeholders}} in template using article data."""
    ctx = build_card_context(
        article,
        scope=scope,
        title_override=title_override,
        subtitle_override=subtitle_override,
        image_url=image_url,
    )
    result = template
    for key, value in ctx.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def render_card_html(
    article: dict[str, Any],
    template_name: str = "card.html",
    scope: str | None = None,
    title_override: str | None = None,
    subtitle_override: str | None = None,
    image_url: str | None = None,
) -> str:
    """Render card to an HTML string without requiring Playwright."""
    ensure_dirs()
    if not article.get("title"):
        raise ValueError("Artigo deve ter titulo para gerar card")
    if not article.get("source"):
        raise ValueError("Artigo deve ter fonte para gerar card")

    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    template = template_path.read_text(encoding="utf-8")
    return _render_html(
        article,
        template,
        scope=scope,
        title_override=title_override,
        subtitle_override=subtitle_override,
        image_url=image_url,
    )


def save_card_html(article_id: str, html: str) -> Path:
    """Persist the rendered HTML to data/cards/ for audit trail.

    Returns the path where the file was saved.
    """
    ensure_dirs()
    html_path = CARDS_DIR / f"card_{article_id[:16]}.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def _chromium_executable() -> str | None:
    """Detect a usable Chromium executable path.

    Checks (in order):
    1. PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH env var (explicit override)
    2. CHROMIUM_PATH env var (legacy Docker setting)
    3. System PATH via shutil.which
    Returns None to let Playwright use its own bundled binary (default).
    """
    for candidate in (
        os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"),
        os.environ.get("CHROMIUM_PATH"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def is_playwright_available() -> bool:
    """Return True if Playwright + Chromium can launch successfully."""
    try:
        from playwright.sync_api import sync_playwright

        exec_path = _chromium_executable()
        launch_kwargs = {"executable_path": exec_path} if exec_path else {}
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            browser.close()
        return True
    except Exception:
        return False


def list_templates() -> list[str]:
    """List card templates (card*.html) available in the templates/ directory."""
    if not TEMPLATES_DIR.exists():
        return ["card.html"]
    names = sorted(p.name for p in TEMPLATES_DIR.glob("card*.html"))
    return names if names else ["card.html"]


def render_cards(
    scope: str = "piaui",
    limit: int = 5,
    article_ids: list[str] | None = None,
    template_name: str = "card.html",
) -> list[dict[str, Any]]:
    """Render cards for a list of articles or the pending queue.

    For each valid article:
    1. Renders HTML and saves it to data/cards/ (audit trail).
    2. Attempts Playwright PNG generation.
    3. If Playwright is unavailable, returns HTML-only results and logs a warning.

    Returns a list of dicts with keys: article_id, title, card_path, html_path.
    card_path is None when Playwright is unavailable.
    """
    ensure_dirs()
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    template = template_path.read_text(encoding="utf-8")

    if article_ids:
        from news_radar.core.db import connect

        with connect() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(article_ids))
            cur.execute(
                f"SELECT * FROM articles WHERE id IN ({ph})", article_ids
            )
            articles = [dict(r) for r in cur.fetchall()]
    else:
        articles = articles_pending_card(scope=scope, limit=limit)

    if not articles:
        return []

    valid_articles = [a for a in articles if a.get("title") and a.get("source")]
    if not valid_articles:
        logger.warning("Nenhum artigo valido para gerar card (sem titulo ou fonte)")
        return []

    # Render and save HTML for all valid articles before attempting Playwright
    rendered: list[tuple[dict, str, Path]] = []
    for article in valid_articles:
        html = _render_html(article, template, scope=scope)
        html_path = save_card_html(article["id"], html)
        rendered.append((article, html, html_path))

    generated: list[dict[str, Any]] = []

    try:
        from playwright.sync_api import sync_playwright

        exec_path = _chromium_executable()
        launch_kwargs = {"executable_path": exec_path} if exec_path else {}
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 600, "height": 400})

            for article, html, html_path in rendered:
                card_path = CARDS_DIR / f"card_{article['id'][:16]}.png"
                page.set_content(html, wait_until="networkidle")
                page.locator("#card").screenshot(path=str(card_path))

                update_card_status(
                    article["id"],
                    status="pending",
                    card_path=str(card_path),
                    html_path=str(html_path),
                )
                generated.append(
                    {
                        "article_id": article["id"],
                        "title": article.get("title"),
                        "card_path": str(card_path),
                        "html_path": str(html_path),
                    }
                )

            browser.close()

    except Exception as exc:
        logger.warning(
            "Playwright indisponivel — gerado apenas HTML: %s", exc
        )
        for article, _html, html_path in rendered:
            update_card_status(
                article["id"],
                status="pending",
                card_path=None,
                html_path=str(html_path),
            )
            generated.append(
                {
                    "article_id": article["id"],
                    "title": article.get("title"),
                    "card_path": None,
                    "html_path": str(html_path),
                    "playwright_error": str(exc)[:200],
                }
            )

    return generated


def render_single_card(
    article_id: str,
    image_url: str | None = None,
    template_name: str = "card.html",
) -> dict[str, Any]:
    """Renderiza um único card pra PNG. Usado pela rota /cards/render."""
    from news_radar.core.db import connect

    ensure_dirs()
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
        row = cur.fetchone()

    if row is None:
        raise LookupError(f"Artigo {article_id} não encontrado")

    article = dict(row)
    if not article.get("title") or not article.get("source"):
        raise ValueError("Artigo precisa de title e source")

    template = template_path.read_text(encoding="utf-8")
    html = _render_html(article, template, image_url=image_url)
    html_path = save_card_html(article_id, html)

    card_path = CARDS_DIR / f"card_{article_id[:16]}.png"

    try:
        from playwright.sync_api import sync_playwright

        exec_path = _chromium_executable()
        launch_kwargs = {"executable_path": exec_path} if exec_path else {}
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 600, "height": 800})
            page.set_content(html, wait_until="networkidle")
            page.locator("#card").screenshot(path=str(card_path))
            browser.close()
    except Exception as exc:
        return {
            "ok": False,
            "article_id": article_id,
            "html_path": str(html_path),
            "error": f"playwright: {str(exc)[:200]}",
        }

    update_card_status(article_id, status="pending", card_path=str(card_path), html_path=str(html_path))

    return {
        "ok": True,
        "article_id": article_id,
        "card_path": str(card_path),
        "html_path": str(html_path),
    }
