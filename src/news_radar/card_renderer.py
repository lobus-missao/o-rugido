from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CARDS_DIR, TEMPLATES_DIR, ensure_dirs
from .repository import articles_pending_card, update_card_status


def _render_html(article: dict[str, Any], template: str) -> str:
    ai_json = article.get("ai_json") or {}
    if isinstance(ai_json, str):
        try:
            ai_json = json.loads(ai_json)
        except Exception:
            ai_json = {}

    # Prioridade
    priority = (article.get("priority") or "").lower()
    priority_label = {
        "critica": "CRITICA", "alta": "ALTA", "media": "MEDIA",
        "baixa": "BAIXA", "ruido": "RUIDO",
    }.get(priority, priority.upper() or "?")
    priority_color = {
        "critica": "#dc2626", "alta": "#ea580c", "media": "#d97706",
        "baixa": "#16a34a", "ruido": "#6b7280",
    }.get(priority, "#6b7280")

    # Pontos-chave
    pontos_chave = ai_json.get("pontos_chave") or []
    if isinstance(pontos_chave, str):
        pontos_chave = [pontos_chave]
    pontos_html = "".join(f"<li>{p}</li>" for p in pontos_chave[:4])

    # Resumo
    resumo = (ai_json.get("resumo_curto") or article.get("summary") or "")[:200]

    # Score
    score = float(article.get("final_score_brasil") or article.get("final_score_piaui") or
                  article.get("final_score_teresina") or 0)

    # Badge IA ou Auto
    ia_badge = "IA" if article.get("ai_score") else "AUTO"

    # Localidade
    localidade = ai_json.get("localidade") or article.get("locality") or ""
    localidade_tag = f'<span class="tag local">{localidade}</span>' if localidade else ""

    # Entidades (máx 3)
    entidades = ai_json.get("entidades") or []
    if isinstance(entidades, str):
        try:
            entidades = json.loads(entidades)
        except Exception:
            entidades = [entidades]
    entidades_tags = "".join(
        f'<span class="tag entidade">{e}</span>'
        for e in entidades[:3]
    )

    # Riqueza de conteúdo
    summary_len = len(article.get("summary") or "")
    if summary_len >= 500:
        conteudo_tag = f'<span class="tag conteudo-rico">Conteudo rico ({summary_len} chars)</span>'
    elif summary_len >= 200:
        conteudo_tag = f'<span class="tag conteudo-medio">Conteudo medio ({summary_len} chars)</span>'
    elif summary_len >= 50:
        conteudo_tag = f'<span class="tag conteudo-simples">Conteudo simples ({summary_len} chars)</span>'
    else:
        conteudo_tag = '<span class="tag conteudo-simples">Sem resumo</span>'

    # Justificativa
    justif = ai_json.get("justificativa_score") or ""
    justificativa_html = f'<div class="justificativa">{justif[:140]}</div>' if justif else ""

    return (
        template
        .replace("{{titulo}}", article.get("title") or "")
        .replace("{{editoria}}", article.get("category") or "-")
        .replace("{{prioridade}}", priority_label)
        .replace("{{prioridade_cor}}", priority_color)
        .replace("{{resumo}}", resumo)
        .replace("{{pontos_chave}}", pontos_html)
        .replace("{{fonte}}", article.get("source") or "")
        .replace("{{data}}", str(article.get("published_at") or "")[:10])
        .replace("{{score}}", f"{score:.0f}")
        .replace("{{ia_badge}}", ia_badge)
        .replace("{{localidade_tag}}", localidade_tag)
        .replace("{{entidades_tags}}", entidades_tags)
        .replace("{{conteudo_tag}}", conteudo_tag)
        .replace("{{justificativa_html}}", justificativa_html)
    )


def render_cards(
    scope: str = "brasil",
    limit: int = 5,
    article_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    ensure_dirs()
    template_path = TEMPLATES_DIR / "card.html"
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    template = template_path.read_text(encoding="utf-8")

    if article_ids:
        # Renderiza artigos específicos (fluxo de dispatch)
        from .db import connect
        with connect() as conn:
            with conn.cursor() as cur:
                ph = ",".join(["%s"] * len(article_ids))
                cur.execute(f"SELECT * FROM articles WHERE id IN ({ph})", article_ids)
                articles = [dict(r) for r in cur.fetchall()]
    else:
        articles = articles_pending_card(scope=scope, limit=limit)

    if not articles:
        return []

    from playwright.sync_api import sync_playwright

    generated = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 600, "height": 400})

        for article in articles:
            html = _render_html(article, template)
            card_path = CARDS_DIR / f"card_{article['id'][:16]}.png"

            page.set_content(html, wait_until="networkidle")
            page.locator("#card").screenshot(path=str(card_path))

            update_card_status(article["id"], status="pending", card_path=str(card_path))
            generated.append({
                "article_id": article["id"],
                "title": article.get("title"),
                "card_path": str(card_path),
            })

        browser.close()

    return generated
