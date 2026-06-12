from __future__ import annotations

import logging
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from news_radar.core.config import CARDS_DIR, TEMPLATES_DIR, ensure_dirs
from news_radar.core.text_utils import strip_source_suffix

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
    """
    # ── Título ─────────────────────────────────────────────────────────────────
    titulo = strip_source_suffix(title_override or article.get("title") or "")

    # ── Subtítulo (card-editorial-base.html) ───────────────────────────────────
    subtitulo_raw = (subtitle_override or "").strip()
    subtitulo_html = (
        f'<div class="card-subtitulo">{subtitulo_raw}</div>' if subtitulo_raw else ""
    )

    # ── Prioridade ─────────────────────────────────────────────────────────────
    priority = (article.get("priority") or "").lower()
    priority_label = _PRIORITY_LABEL.get(priority, priority.upper() or "?")
    priority_color = _PRIORITY_COLOR.get(priority, "#6b7280")

    # ── Editoria / Categoria ───────────────────────────────────────────────────
    category = article.get("category") or "-"
    categoria_tag = (
        f'<span class="tag tag-categoria">{category}</span>'
        if category and category != "-"
        else ""
    )

    # ── Resumo ─────────────────────────────────────────────────────────────────
    summary_override = (article.get("__summary_override") or "").strip()
    resumo_raw = summary_override or article.get("summary") or ""
    resumo = resumo_raw[:200]

    # ── Localidade ─────────────────────────────────────────────────────────────
    localidade = article.get("locality") or ""
    localidade_tag = (
        f'<span class="tag local">{localidade}</span>' if localidade else ""
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

    hero_url = (image_url or "").strip()
    hero_empty_class = "" if hero_url else " empty"

    return {
        "titulo": titulo,
        "subtitulo_html": subtitulo_html,
        "editoria": category,
        "prioridade": priority_label,
        "prioridade_cor": priority_color,
        "resumo": resumo,
        "pontos_chave": "",
        "pontos_html": "",
        "fonte": article.get("source") or "",
        "data": str(article.get("published_at") or "")[:10],
        "localidade_tag": localidade_tag,
        "entidades_tags": "",
        "categoria_tag": categoria_tag,
        "conteudo_tag": conteudo_tag,
        "justificativa_html": "",
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


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VALID_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _image_extension_from(url: str, content_type: str | None) -> str | None:
    """Determina extensão a partir do Content-Type (preferencial) ou URL."""
    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        if mime not in _VALID_IMAGE_MIMES:
            return None  # SVG, HTML, etc — rejeita
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            ext = guessed.lower()
            if ext == ".jpe":
                ext = ".jpg"
            if ext in _IMAGE_EXTS:
                return ext
    path = urlparse(url).path.lower()
    for ext in _IMAGE_EXTS:
        if path.endswith(ext):
            return ext
    return None


def _find_cached_post_image(article_id: str) -> Path | None:
    """Retorna o arquivo `post_<id>.*` já baixado, se existir."""
    for ext in _IMAGE_EXTS:
        cached = CARDS_DIR / f"post_{article_id[:16]}{ext}"
        if cached.exists() and cached.stat().st_size > 0:
            return cached
    return None


def download_post_image(image_url: str, article_id: str) -> Path | None:
    """Baixa a imagem do post pro disco. Rejeita SVG/HTML/conteúdo inválido."""
    if not image_url:
        return None
    try:
        resp = requests.get(
            image_url,
            timeout=15,
            headers={"User-Agent": "news-radar/1.0"},
            allow_redirects=True,
        )
        resp.raise_for_status()
        ext = _image_extension_from(image_url, resp.headers.get("Content-Type"))
        if not ext:
            logger.warning(
                "tipo invalido (Content-Type=%s) em %s",
                resp.headers.get("Content-Type"),
                image_url,
            )
            return None
        dest = CARDS_DIR / f"post_{article_id[:16]}{ext}"
        dest.write_bytes(resp.content)
        return dest
    except Exception as exc:
        logger.warning("falha ao baixar imagem %s: %s", image_url, exc)
        return None


def render_cards(
    scope: str = "piaui",
    limit: int = 5,
    article_ids: list[str] | None = None,
    template_name: str = "card.html",
) -> list[dict[str, Any]]:
    """Prepara imagens dos posts pendentes. Delega pro render_single_card."""
    ensure_dirs()

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

    valid = [a for a in articles if a.get("title") and a.get("source")]
    if not valid:
        return []

    generated: list[dict[str, Any]] = []
    for art in valid:
        r = render_single_card(art["id"])
        if r.get("ok"):
            generated.append({
                "article_id": art["id"],
                "title": art.get("title"),
                "card_path": r.get("card_path"),
            })
        else:
            generated.append({
                "article_id": art["id"],
                "title": art.get("title"),
                "card_path": None,
                "error": r.get("error"),
            })
    return generated


def render_single_card(
    article_id: str,
    image_url: str | None = None,
    template_name: str = "card-post.html",
    *,
    title_override: str | None = None,
    summary_override: str | None = None,  # não afeta a imagem (vai pro caption)
) -> dict[str, Any]:
    """Gera o card visual (PNG) com foto de fundo + banner de manchete."""
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

    # Cache: se não veio URL explícita E já temos imagem baixada, usa cache.
    # Se veio URL explícita, baixa de novo (editor pode ter trocado a imagem).
    local_image: Path | None = None
    if not image_url:
        local_image = _find_cached_post_image(article_id)

    if local_image is None:
        candidates: list[str] = []
        if image_url:
            candidates.append(image_url)
        else:
            from news_radar.services.image_search import search_images
            candidates.extend(
                item["url"] for item in search_images(article["title"], limit=8)
                if item.get("url")
            )

        if not candidates:
            return {
                "ok": False,
                "article_id": article_id,
                "error": "nenhuma imagem encontrada — use Editar pra escolher",
            }

        for url in candidates:
            local_image = download_post_image(url, article_id)
            if local_image:
                image_url = url
                break

        if not local_image:
            return {
                "ok": False,
                "article_id": article_id,
                "error": f"todas as {len(candidates)} imagens candidatas falharam",
            }
    import base64
    mime = mimetypes.guess_type(str(local_image))[0] or "image/jpeg"
    b64 = base64.b64encode(local_image.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    template = template_path.read_text(encoding="utf-8")
    html = _render_html(article, template, image_url=data_url, title_override=title_override)
    html_path = save_card_html(article_id, html)

    card_path = CARDS_DIR / f"card_{article_id[:16]}.png"

    try:
        from playwright.sync_api import sync_playwright

        exec_path = _chromium_executable()
        launch_kwargs = {"executable_path": exec_path} if exec_path else {}
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
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
        "image_url": image_url,
    }
