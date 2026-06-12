"""
Controle editorial: seleção de top-N → aprovação humana → publicação.

Modelo de edição único (`default`) — uma fila contínua, sem janelas horárias.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from news_radar.core.config import (
    NEWS_RADAR_PUBLIC_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from news_radar.core.db import connect, utc_now
from news_radar.core.text_utils import normalize_text, strip_source_suffix

_GNEWS_GENERIC_PREFIXES = (
    "Comprehensive up-to-date news coverage",
    "Cobertura abrangente e atualizada",
)

_PHOTO_CREDIT_DOMAIN = re.compile(
    r"^(?:Foto|Imagem|Cr[eé]dito|Arte):[^.]*?\.com(?:\.br)?\s+",
    re.IGNORECASE | re.UNICODE,
)
_PHOTO_CREDIT_WORDS = re.compile(
    r"^(?:Foto|Imagem|Cr[eé]dito|Arte):\s+\S+(?:\s+\S+)?\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])",
    re.IGNORECASE | re.UNICODE,
)
_PHOTO_CREDIT_BARE = re.compile(
    r"^(?:Reprodu[cç][aã]o|Divulga[cç][aã]o|Internet)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])",
    re.IGNORECASE | re.UNICODE,
)


def _strip_photo_credit(text: str) -> str:
    """Remove crédito de foto comum no início de resumos jornalísticos."""
    if not text:
        return text
    out = text.strip()
    out = _PHOTO_CREDIT_DOMAIN.sub("", out)
    out = _PHOTO_CREDIT_WORDS.sub("", out)
    out = _PHOTO_CREDIT_BARE.sub("", out)
    return out.strip()


def _summary_is_redundant(title: str, summary: str) -> bool:
    """Detecta feeds (Google News) que repetem o título ou retornam genérico."""
    if not summary or not title:
        return True
    if summary.startswith(_GNEWS_GENERIC_PREFIXES):
        return True
    nt = normalize_text(title)
    ns = normalize_text(summary)
    if not nt or not ns:
        return True
    if nt in ns or ns in nt:
        return True
    title_words = set(nt.split())
    if not title_words:
        return True
    overlap = len(title_words & set(ns.split())) / len(title_words)
    return overlap >= 0.85


def _decode_gnews_url(url: str) -> str | None:
    """Desempacota URL do Google News pra URL real do artigo."""
    if not url or "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(url, interval=1)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception as exc:
        _logger.warning("falha ao decodificar GNews %s: %s", url[:80], str(exc)[:120])
    return None


def _fetch_article_summary(url: str, timeout: int = 10) -> tuple[str, str]:
    """Busca og:description da URL real. Retorna (summary, resolved_url)."""
    if not url:
        return "", ""
    resolved = url
    if "news.google.com" in url:
        decoded = _decode_gnews_url(url)
        if not decoded:
            return "", ""
        resolved = decoded
    try:
        resp = requests.get(
            resolved,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; news-radar/1.0)"},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        _logger.warning("falha ao buscar resumo de %s: %s", resolved, str(exc)[:120])
        return "", resolved

    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return "", resolved

    for selector in (
        ("meta", {"property": "og:description"}),
        ("meta", {"name": "description"}),
        ("meta", {"name": "twitter:description"}),
    ):
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            content = tag["content"].strip()
            if len(content) >= 30 and not content.startswith(_GNEWS_GENERIC_PREFIXES):
                return content, resolved

    article_tag = soup.find("article") or soup
    for p in article_tag.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) >= 60:
            return text, resolved

    return "", resolved


def _persist_article_enrichment(
    article_id: str,
    *,
    summary: str | None = None,
    canonical_url: str | None = None,
) -> None:
    """Salva resumo e/ou URL resolvida no artigo (best-effort)."""
    if not article_id or (not summary and not canonical_url):
        return
    sets, params = [], []
    if summary:
        sets.append("summary = %s")
        params.append(summary)
    if canonical_url:
        sets.append("canonical_url = %s")
        sets.append("url = %s")
        params.extend([canonical_url, canonical_url])
    sets.append("updated_at = NOW()")
    params.append(article_id)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE articles SET {', '.join(sets)} WHERE id = %s",
                tuple(params),
            )
    except Exception as exc:
        _logger.warning(
            "falha ao persistir enrichment de %s: %s", article_id, str(exc)[:120]
        )

_logger = logging.getLogger(__name__)

EDITIONS = {
    "default": {"label": "Dispatch", "dispatch_hour": 7, "dispatch_min": 0, "post_hour": 7},
}

# Janela de coleta (horas para trás a partir do disparo).
EDITION_WINDOWS = {
    "default": 24,
}

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _is_dry_run(dry_run: bool | None = None) -> bool:
    if dry_run is not None:
        return dry_run
    return os.getenv("NEWS_RADAR_DRY_RUN", "").lower() in {"1", "true", "yes", "on"}


def _tg(method: str, **kwargs) -> dict:
    if _is_dry_run():
        return {"ok": True, "dry_run": True, "result": {"message_id": 0, "method": method}}
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    r = requests.post(f"{API}/{method}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _try_record_editorial_action(
    action: str,
    actor: str,
    article_id: str | None = None,
    dispatch_id: int | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str | None = None,
) -> None:
    """Registra ação editorial (best-effort). Não quebra o fluxo se a tabela não existir."""
    try:
        from news_radar.repositories.editorial_actions import record_editorial_action
        record_editorial_action(
            action=action,
            actor=actor,
            article_id=article_id,
            dispatch_id=dispatch_id,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
        )
    except Exception as exc:
        _logger.warning(
            "Falha ao registrar ação editorial '%s' (dispatch=%s): %s",
            action,
            dispatch_id,
            str(exc)[:120],
        )


def _try_update_article_editorial_status(article_id: str, status: str) -> None:
    """Atualiza editorial_status do artigo (best-effort). Não quebra o fluxo em caso de falha."""
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE articles SET editorial_status=%s, updated_at=NOW() WHERE id=%s",
                (status, article_id),
            )
    except Exception as exc:
        _logger.warning(
            "Falha ao atualizar editorial_status='%s' para article_id=%s: %s",
            status,
            article_id,
            str(exc)[:120],
        )


def get_dispatch(dispatch_id: int) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM dispatches WHERE id = %s", (dispatch_id,))
        row = cur.fetchone()
    return dict(row) if row else None


_EDIT_TOKEN_TTL_HOURS = 24


def ensure_edit_token(dispatch_id: int, ttl_hours: int = _EDIT_TOKEN_TTL_HOURS) -> str:
    """Gera (ou recupera) token de edição único do dispatch.

    Retorna o token. Idempotente: se já existir e ainda for válido, devolve o mesmo.
    """
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        raise LookupError(f"dispatch {dispatch_id} nao encontrado")

    existing = dispatch.get("edit_token")
    expires_at = dispatch.get("edit_token_expires_at")
    now = utc_now()
    if existing and expires_at and expires_at > now:
        return existing

    token = secrets.token_urlsafe(24)
    new_expires = now + timedelta(hours=ttl_hours)
    update_dispatch(
        dispatch_id,
        edit_token=token,
        edit_token_expires_at=new_expires,
    )
    return token


def edit_url_for(dispatch_id: int) -> str | None:
    """URL pública /edit?token=... usada nos botões do Telegram."""
    if not NEWS_RADAR_PUBLIC_URL:
        return None
    token = ensure_edit_token(dispatch_id)
    return f"{NEWS_RADAR_PUBLIC_URL}/edit?token={token}"


def get_dispatch_by_token(token: str) -> dict | None:
    """Resolve token → dispatch + article. None se inválido ou expirado."""
    token = (token or "").strip()
    if not token:
        return None
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.*, a.title AS article_title, a.summary AS article_summary,
                   a.source AS article_source, a.url AS article_url,
                   a.canonical_url AS article_canonical_url,
                   a.published_at AS article_published_at,
                   a.priority AS article_priority,
                   a.category AS article_category,
                   a.final_score_piaui AS article_score
            FROM dispatches d
            JOIN articles a ON a.id = d.article_id
            WHERE d.edit_token = %s
            """,
            (token,),
        )
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    expires_at = row.get("edit_token_expires_at")
    if expires_at and expires_at < utc_now():
        return None
    return row


def apply_edit(
    dispatch_id: int,
    *,
    title: str | None = None,
    summary: str | None = None,
    image_url: str | None = None,
    user: str = "Editor",
) -> dict:
    """Persiste edições do editor no dispatch. Não regera o card aqui."""
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado"}

    fields: dict = {}
    if title is not None:
        fields["edited_title"] = title.strip() or None
    if summary is not None:
        fields["edited_summary"] = summary.strip() or None
    if image_url is not None:
        fields["image_url"] = image_url.strip() or None

    if not fields:
        return {"ok": True, "dispatch_id": dispatch_id, "skipped": True}

    update_dispatch(dispatch_id, **fields)

    _try_record_editorial_action(
        action="edit_dispatch",
        actor=user,
        article_id=dispatch.get("article_id"),
        dispatch_id=dispatch_id,
        notes=", ".join(sorted(fields.keys())),
    )
    return {"ok": True, "dispatch_id": dispatch_id, "updated": list(fields.keys())}


def apply_edit_and_refresh(
    dispatch_id: int,
    *,
    title: str | None = None,
    summary: str | None = None,
    image_url: str | None = None,
    user: str = "Editor",
) -> dict:
    """Aplica edits e, se o card já existe no Telegram, re-renderiza e troca a foto."""
    from news_radar.services.rendering import render_single_card

    result = apply_edit(
        dispatch_id, title=title, summary=summary, image_url=image_url, user=user
    )
    if not result.get("ok"):
        return result

    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return result

    needs_regen = dispatch.get("status") in ("pending_card", "card_rejected")
    if not needs_regen:
        return {**result, "regenerated": False}

    try:
        r = render_single_card(
            dispatch["article_id"],
            image_url=dispatch.get("image_url"),
            title_override=dispatch.get("edited_title"),
            summary_override=dispatch.get("edited_summary"),
        )
    except Exception as exc:
        return {**result, "regenerated": False, "error": str(exc)[:200]}

    if not r.get("ok") or not r.get("card_path"):
        return {**result, "regenerated": False, "error": r.get("error")}

    update_dispatch(dispatch_id, card_path=r["card_path"])
    _swap_telegram_card_photo(
        dispatch.get("card_tg_message_id"), r["card_path"], dispatch_id, user
    )
    return {**result, "regenerated": True, "card_path": r["card_path"]}


def _swap_telegram_card_photo(
    message_id: str | None,
    card_path: str,
    dispatch_id: int,
    user: str,
) -> None:
    """Troca a foto da mensagem do card via editMessageMedia (mantém os botões)."""
    if not message_id or _is_dry_run():
        return
    keyboard_row = [
        {"text": "✅ Publicar",    "callback_data": f"card_approve:{dispatch_id}"},
        {"text": "🔄 Regerar",     "callback_data": f"card_regenerate:{dispatch_id}"},
        {"text": "❌ Rejeitar",    "callback_data": f"card_reject:{dispatch_id}"},
    ]
    edit_url = edit_url_for(dispatch_id)
    if edit_url:
        keyboard_row.insert(1, {"text": "✏️ Editar", "url": edit_url})

    dispatch_full = get_dispatch_with_article(dispatch_id) or {}
    caption = _build_post_caption(dispatch_full)
    media = {
        "type": "photo",
        "media": "attach://card",
        "caption": caption,
        "parse_mode": "Markdown",
    }
    try:
        with open(card_path, "rb") as photo:
            r = requests.post(
                f"{API}/editMessageMedia",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "message_id": int(message_id),
                    "media": json.dumps(media),
                    "reply_markup": json.dumps({"inline_keyboard": [keyboard_row]}),
                },
                files={"card": photo},
                timeout=30,
            )
            r.raise_for_status()
    except Exception as exc:
        _logger.warning("editMessageMedia falhou: %s", str(exc)[:200])


def get_dispatch_with_article(dispatch_id: int) -> dict | None:
    """Retorna `{dispatch, article, card_path}` ou None se dispatch não existir."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT d.*, a.title AS article_title, a.url AS article_url,
                       a.final_score_piaui, a.priority, a.category, a.card_path
                FROM dispatches d
                JOIN articles a ON a.id = d.article_id
                WHERE d.id = %s
                """,
            (dispatch_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    return {
        "dispatch": {k: v for k, v in row.items() if not k.startswith("article_") and k != "card_path"},
        "article": {
            "id": row.get("article_id"),
            "title": row.get("article_title"),
            "url": row.get("article_url"),
            "priority": row.get("priority"),
            "category": row.get("category"),
            "final_score_piaui": row.get("final_score_piaui"),
        },
        "card_path": row.get("card_path"),
    }


def update_dispatch(dispatch_id: int, **fields) -> None:
    fields["updated_at"] = utc_now()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = [*fields.values(), dispatch_id]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE dispatches SET {set_clause} WHERE id = %s", values)


def _try_claim_dispatch(dispatch_id: int, from_status: str, to_status: str) -> bool:
    """
    UPDATE atômico com WHERE status = from_status.
    Retorna True se a linha foi atualizada (claim bem-sucedido).
    Resolve race condition em callbacks Telegram: dois cliques simultâneos
    disputam o UPDATE — apenas o primeiro vence, o segundo retorna False.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE dispatches SET status = %s, updated_at = %s "
            "WHERE id = %s AND status = %s",
            (to_status, utc_now(), dispatch_id, from_status),
        )
        return cur.rowcount == 1


def get_edition_dispatches(edition: str, edition_date: date) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT d.*, a.title, a.source, a.summary, a.final_score_piaui,
                       a.priority, a.card_path, a.canonical_url, a.published_at
                FROM dispatches d
                JOIN articles a ON d.article_id = a.id
                WHERE d.edition = %s AND d.edition_date = %s
                ORDER BY d.rank
            """, (edition, edition_date))
        return [dict(r) for r in cur.fetchall()]


def get_today_editions() -> dict[str, list[dict]]:
    today = date.today()
    result = {}
    for edition in EDITIONS:
        result[edition] = get_edition_dispatches(edition, today)
    return result


def select_top_articles(edition: str, scope: str = "piaui", top: int = 3) -> list[dict]:
    """Seleciona os melhores artigos para a edição, excluindo já despachados hoje."""
    window_hours = EDITION_WINDOWS.get(edition, 6)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    score_col = f"final_score_{scope}"
    today = date.today()

    with connect() as conn, conn.cursor() as cur:
        # Artigos já despachados hoje
        cur.execute("""
                SELECT article_id FROM dispatches
                WHERE edition_date = %s
            """, (today,))
        already = {row["article_id"] for row in cur.fetchall()}

        cur.execute(f"""
                SELECT *
                FROM articles
                WHERE (published_at >= %s OR published_at IS NULL)
                  AND {score_col} > 0
                  AND card_status NOT IN ('rejected')
                  AND editorial_status NOT IN ('rejected', 'archived')
                ORDER BY {score_col} DESC, published_at DESC NULLS LAST
                LIMIT 50
            """, (cutoff,))
        candidates = [dict(r) for r in cur.fetchall()]

    pool = [a for a in candidates if a["id"] not in already]
    return _select_with_diversity(pool, top)


def _select_with_diversity(candidates: list[dict], top: int) -> list[dict]:
    """Top-N com diversidade — evita 3 matérias da mesma história/editoria.

    Ordem: maior score primeiro; cada próximo precisa ter title_signature
    diferente dos já escolhidos e, preferencialmente, categoria diferente.
    """
    if top <= 0 or not candidates:
        return []

    selected: list[dict] = []
    seen_signatures: set[str] = set()
    seen_categories: set[str] = set()

    # 1ª passada: exige diversidade de história E de editoria
    for art in candidates:
        if len(selected) >= top:
            break
        sig = art.get("title_signature") or ""
        cat = (art.get("category") or "").strip()
        if sig and sig in seen_signatures:
            continue
        if cat and cat in seen_categories:
            continue
        selected.append(art)
        if sig:
            seen_signatures.add(sig)
        if cat:
            seen_categories.add(cat)

    # 2ª passada: relaxa editoria, mantém dedupe de história
    if len(selected) < top:
        chosen_ids = {a["id"] for a in selected}
        for art in candidates:
            if len(selected) >= top:
                break
            if art["id"] in chosen_ids:
                continue
            sig = art.get("title_signature") or ""
            if sig and sig in seen_signatures:
                continue
            selected.append(art)
            chosen_ids.add(art["id"])
            if sig:
                seen_signatures.add(sig)

    return selected


def create_dispatch(
    edition: str,
    scope: str = "piaui",
    top: int = 3,
    dry_run: bool | None = None,
) -> list[dict]:
    """
    Cria registros de dispatch para a edição e envia pro Telegram.
    Retorna os dispatches criados.

    Idempotente: chamadas repetidas para a mesma edição/data/scope com dispatches
    ativos retornam [] sem duplicar envios ao Telegram.
    """
    if edition not in EDITIONS:
        raise ValueError(f"edition deve ser uma destas: {list(EDITIONS.keys())}")

    today = date.today()

    # Guard de idempotência: impede duplo envio ao Telegram se n8n e scheduler
    # interno dispararem simultaneamente. Verifica dispatches ativos (não rejeitados).
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT COUNT(*) AS cnt FROM dispatches
                WHERE edition = %s
                  AND edition_date = %s
                  AND scope = %s
                  AND status NOT IN ('article_rejected', 'card_rejected')
                """,
            (edition, today, scope),
        )
        if cur.fetchone()["cnt"] > 0:
            _logger.warning(
                "Dispatch bloqueado (idempotência): edição '%s' já existe para %s"
                " scope=%s. Chamada duplicada ignorada.",
                edition,
                today,
                scope,
            )
            return []

    articles = select_top_articles(edition, scope, top)
    if not articles:
        return []

    edition_info = EDITIONS[edition]
    created = []

    with connect() as conn, conn.cursor() as cur:
        for rank, art in enumerate(articles, start=1):
            cur.execute("""
                    INSERT INTO dispatches
                    (article_id, edition, edition_date, rank, scope, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 'pending_article', NOW(), NOW())
                    RETURNING id
                """, (art["id"], edition, today, rank, scope))
            dispatch_id = cur.fetchone()["id"]
            created.append({"dispatch_id": dispatch_id, "article": art, "rank": rank})

    # Envia cabeçalho da edição
    edition_label = edition_info["label"]
    previous_dry_run = os.getenv("NEWS_RADAR_DRY_RUN")
    if dry_run is not None:
        os.environ["NEWS_RADAR_DRY_RUN"] = "1" if dry_run else "0"
    try:
        _tg("sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"📰 *EDIÇÃO {edition_label.upper()}*\n\nSelecionei {len(created)} notícia(s) para aprovação editorial. Aprove ou rejeite cada uma:",
            "parse_mode": "Markdown",
        })

        # Envia cada artigo para aprovação
        for item in created:
            dispatch_id = item["dispatch_id"]
            art = item["article"]
            rank = item["rank"]
            _send_article_for_approval(dispatch_id, art, rank, edition_label)
    finally:
        if dry_run is not None:
            if previous_dry_run is None:
                os.environ.pop("NEWS_RADAR_DRY_RUN", None)
            else:
                os.environ["NEWS_RADAR_DRY_RUN"] = previous_dry_run

    return created


def _send_article_for_approval(dispatch_id: int, art: dict, rank: int, edition_label: str) -> None:
    from news_radar.services.rendering import render_single_card

    # Gera o card (foto + design) upfront pra editor já ver como vai ficar
    r = render_single_card(art["id"])
    card_path = r.get("card_path") if r.get("ok") else None
    if card_path:
        update_dispatch(dispatch_id, card_path=card_path)
    if r.get("image_url"):
        update_dispatch(dispatch_id, image_url=r["image_url"])

    raw_summary = _strip_photo_credit((art.get("summary") or "").strip())
    url = art.get("url") or art.get("canonical_url") or ""
    title = strip_source_suffix(art.get("title") or "")[:200]

    # Se o feed só repete o título (GNews), decodifica + busca og:description
    if _summary_is_redundant(title, raw_summary):
        fetched, resolved_url = _fetch_article_summary(url)
        fetched = _strip_photo_credit(fetched) if fetched else ""
        if resolved_url and resolved_url != url:
            _persist_article_enrichment(
                art.get("id"), summary=fetched or None, canonical_url=resolved_url
            )
            url = resolved_url
        elif fetched:
            _persist_article_enrichment(art.get("id"), summary=fetched)
        resumo = fetched[:400] if fetched else ""
    else:
        resumo = raw_summary[:400]

    parts = []
    if resumo:
        parts.append(resumo)
    if url:
        if parts:
            parts.append("")
        parts.append(f"[Ler matéria original]({url})")
    caption = "\n".join(parts)[:1024]

    keyboard_row = [
        {"text": "✅ Aprovar",  "callback_data": f"dispatch_approve:{dispatch_id}"},
        {"text": "❌ Rejeitar", "callback_data": f"dispatch_reject:{dispatch_id}"},
    ]
    edit_url = edit_url_for(dispatch_id)
    if edit_url:
        keyboard_row.insert(1, {"text": "✏️ Editar", "url": edit_url})

    if card_path and Path(card_path).exists():
        with open(card_path, "rb") as photo:
            result = _tg("sendPhoto", data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps({"inline_keyboard": [keyboard_row]}),
            }, files={"photo": photo})
    else:
        result = _tg("sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption + "\n\n⚠️ Imagem nao encontrada — use Editar pra escolher.",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [keyboard_row]},
        })

    msg_id = str(result.get("result", {}).get("message_id", ""))
    update_dispatch(dispatch_id, article_tg_message_id=msg_id, card_tg_message_id=msg_id)


def approve_article(
    dispatch_id: int,
    user: str = "Editor",
    *,
    generate_card: bool = True,
    dry_run: bool | None = None,
    notes: str | None = None,
) -> dict:
    """Aprova o dispatch — vai direto pra ready_to_publish (sem etapa 2)."""
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    if dispatch["status"] not in ("pending_article",):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    if not _try_claim_dispatch(dispatch_id, "pending_article", "ready_to_publish"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": "ready_to_publish"}

    now = utc_now()
    update_kwargs: dict = dict(
        status="ready_to_publish",
        article_reviewed_by=user,
        article_reviewed_at=now,
        card_reviewed_by=user,
        card_reviewed_at=now,
        ready_at=now,
    )
    if notes:
        update_kwargs["review_notes"] = notes
    update_dispatch(dispatch_id, **update_kwargs)

    _try_update_article_editorial_status(dispatch["article_id"], "ready_to_publish")

    _try_record_editorial_action(
        action="approve_dispatch",
        actor=user,
        article_id=dispatch.get("article_id"),
        dispatch_id=dispatch_id,
        from_status="pending_article",
        to_status="ready_to_publish",
        notes=notes,
    )

    _edit_article_message(
        dispatch.get("article_tg_message_id"),
        status_text="✅ APROVADO — PRONTO PRA PUBLICAR",
        user=user,
    )

    return {"ok": True, "dispatch_id": dispatch_id, "status": "ready_to_publish"}


def generate_card_for_dispatch(
    dispatch_id: int,
    user: str = "Editor",
    *,
    dry_run: bool | None = None,
) -> dict:
    from news_radar.services.rendering import render_single_card

    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}
    if dispatch["status"] not in ("article_approved", "pending_card", "card_rejected"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    card_path = None
    error_msg = None
    image_url = dispatch.get("image_url")

    try:
        r = render_single_card(dispatch["article_id"], image_url=image_url)
        if r.get("ok"):
            card_path = r.get("card_path")
            # Persiste image_url quando veio do search automático
            if r.get("image_url") and not image_url:
                update_dispatch(dispatch_id, image_url=r["image_url"])
        else:
            error_msg = r.get("error")
    except Exception as e:
        error_msg = str(e)[:200]

    if card_path and Path(card_path).exists():
        update_dispatch(dispatch_id, status="pending_card", card_path=card_path)
        _send_card_for_approval(dispatch_id, card_path, user, dry_run=dry_run)
        return {
            "ok": True,
            "dispatch_id": dispatch_id,
            "status": "pending_card",
            "card_path": card_path,
        }
    else:
        msg = "⚠️ Artigo aprovado! Card não gerado automaticamente."
        if error_msg:
            msg += f"\nErro: `{error_msg}`"
        msg += f"\nDispatch ID: `{dispatch_id}` — gere pelo dashboard."
        _tg("sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        })
        return {"ok": False, "dispatch_id": dispatch_id, "status": dispatch["status"], "error": error_msg}


def reject_article(dispatch_id: int, user: str = "Editor", notes: str | None = None) -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    if dispatch["status"] not in ("pending_article",):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    if not _try_claim_dispatch(dispatch_id, "pending_article", "article_rejected"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": "article_rejected"}

    update_kwargs: dict = dict(
        status="article_rejected",
        article_reviewed_by=user,
        article_reviewed_at=utc_now(),
    )
    if notes:
        update_kwargs["review_notes"] = notes
    update_dispatch(dispatch_id, **update_kwargs)

    _try_record_editorial_action(
        action="reject_article",
        actor=user,
        article_id=dispatch.get("article_id"),
        dispatch_id=dispatch_id,
        from_status="pending_article",
        to_status="article_rejected",
        notes=notes,
    )
    _edit_article_message(
        dispatch.get("article_tg_message_id"),
        status_text="❌ REJEITADO",
        user=user,
    )
    return {"ok": True, "dispatch_id": dispatch_id, "status": "article_rejected"}


def _build_post_caption(dispatch_with_article: dict) -> str:
    """Monta o caption do post (Telegram/Insta): título, resumo, fonte, link."""
    title = strip_source_suffix(
        dispatch_with_article.get("edited_title")
        or dispatch_with_article.get("article_title")
        or dispatch_with_article.get("title")
        or ""
    )[:200]
    raw_summary = _strip_photo_credit(
        (
            dispatch_with_article.get("edited_summary")
            or dispatch_with_article.get("article_summary")
            or dispatch_with_article.get("summary")
            or ""
        ).strip()
    )
    url = (
        dispatch_with_article.get("article_url")
        or dispatch_with_article.get("url")
        or dispatch_with_article.get("article_canonical_url")
        or dispatch_with_article.get("canonical_url")
        or ""
    )

    summary = "" if _summary_is_redundant(title, raw_summary) else raw_summary[:400]

    parts = []
    if summary:
        parts.append(summary)
    if url:
        if parts:
            parts.append("")
        parts.append(f"[Ler matéria original]({url})")
    return "\n".join(parts)[:1024]


def _send_card_for_approval(
    dispatch_id: int,
    card_path: str,
    user: str,
    dry_run: bool | None = None,
) -> None:
    if _is_dry_run(dry_run):
        result = {"result": {"message_id": 0}}
        update_dispatch(dispatch_id, card_tg_message_id=str(result["result"]["message_id"]))
        return

    keyboard_row = [
        {"text": "✅ Publicar",    "callback_data": f"card_approve:{dispatch_id}"},
        {"text": "🔄 Regerar",     "callback_data": f"card_regenerate:{dispatch_id}"},
        {"text": "❌ Rejeitar",    "callback_data": f"card_reject:{dispatch_id}"},
    ]
    edit_url = edit_url_for(dispatch_id)
    if edit_url:
        keyboard_row.insert(1, {"text": "✏️ Editar", "url": edit_url})

    dispatch_full = get_dispatch_with_article(dispatch_id) or {}
    caption = _build_post_caption(dispatch_full)

    with open(card_path, "rb") as photo:
        result = _tg("sendPhoto", data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps({"inline_keyboard": [keyboard_row]}),
        }, files={"photo": photo})
    msg_id = str(result.get("result", {}).get("message_id", ""))
    update_dispatch(dispatch_id, card_tg_message_id=msg_id)


def approve_card(dispatch_id: int, user: str = "Editor", notes: str | None = None) -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}
    if dispatch["status"] not in ("pending_card", "card_approved", "ready_to_publish"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    now = utc_now()
    update_kwargs: dict = dict(
        status="ready_to_publish",
        card_reviewed_by=user,
        card_reviewed_at=now,
        ready_at=now,
    )
    if notes:
        update_kwargs["review_notes"] = notes
    update_dispatch(dispatch_id, **update_kwargs)

    _try_record_editorial_action(
        action="approve_card",
        actor=user,
        article_id=dispatch.get("article_id"),
        dispatch_id=dispatch_id,
        from_status="pending_card",
        to_status="ready_to_publish",
        notes=notes,
    )
    _edit_caption_remove_buttons(
        dispatch.get("card_tg_message_id"),
        f"✅ APROVADO para publicação por {user}"
    )
    # Atualiza editorial_status do artigo
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE articles SET editorial_status='ready_to_publish', card_status='approved', updated_at=NOW() WHERE id=%s",
            (dispatch["article_id"],)
        )
    return {"ok": True, "dispatch_id": dispatch_id, "status": "ready_to_publish"}


def reject_card(dispatch_id: int, user: str = "Editor", notes: str | None = None) -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    update_kwargs: dict = dict(
        status="card_rejected",
        card_reviewed_by=user,
        card_reviewed_at=utc_now(),
    )
    if notes:
        update_kwargs["review_notes"] = notes
    update_dispatch(dispatch_id, **update_kwargs)

    _try_record_editorial_action(
        action="reject_card",
        actor=user,
        article_id=dispatch.get("article_id"),
        dispatch_id=dispatch_id,
        from_status="pending_card",
        to_status="card_rejected",
        notes=notes,
    )
    _edit_caption_remove_buttons(
        dispatch.get("card_tg_message_id"),
        f"❌ CARD REJEITADO por {user}"
    )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE articles SET editorial_status='card_rejected', card_status='rejected', updated_at=NOW() WHERE id=%s",
            (dispatch["article_id"],)
        )
    return {"ok": True, "dispatch_id": dispatch_id, "status": "card_rejected"}


def regenerate_card(dispatch_id: int, user: str = "Editor") -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}
    update_dispatch(dispatch_id, status="article_approved")
    result = generate_card_for_dispatch(dispatch_id, user=user)
    if result.get("ok"):
        _edit_caption_remove_buttons(
            dispatch.get("card_tg_message_id"),
            f"🔄 Card regerado por {user} — novo card enviado abaixo"
        )
    return result


def mark_published(
    dispatch_id: int,
    user: str = "Editor",
    notes: str | None = None,
) -> None:
    dispatch = get_dispatch(dispatch_id)
    if dispatch:
        update_kwargs: dict = dict(status="published")
        if notes:
            update_kwargs["review_notes"] = notes
        update_dispatch(dispatch_id, **update_kwargs)

        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE articles SET editorial_status='published', updated_at=NOW() WHERE id=%s",
                (dispatch["article_id"],),
            )
        _try_record_editorial_action(
            action="published",
            actor=user,
            article_id=dispatch.get("article_id"),
            dispatch_id=dispatch_id,
            from_status=dispatch.get("status"),
            to_status="published",
            notes=notes,
        )


def handle_callback_action(action: str, payload: str, user: str = "Editor") -> dict:
    dispatch_id = int(payload)
    if action == "dispatch_approve":
        return approve_article(dispatch_id, user, generate_card=True)
    if action == "dispatch_reject":
        return reject_article(dispatch_id, user)
    if action == "card_approve":
        return approve_card(dispatch_id, user)
    if action == "card_reject":
        return reject_card(dispatch_id, user)
    if action == "card_regenerate":
        return regenerate_card(dispatch_id, user)
    return {"ok": False, "error": f"callback desconhecido: {action}", "dispatch_id": dispatch_id}


def _edit_article_message(message_id: str | None, status_text: str, user: str) -> None:
    """Marca a mensagem (foto ou texto) com status final e remove os botões."""
    if not message_id:
        return
    new_text = f"{status_text} por *{user}*"
    # Mensagem com foto → editMessageCaption
    try:
        _tg("editMessageCaption", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(message_id),
            "caption": new_text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": []},
        })
        return
    except Exception:
        pass
    # Mensagem só texto → editMessageText
    try:
        _tg("editMessageText", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(message_id),
            "text": new_text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception:
        with suppress(Exception):
            _tg("editMessageReplyMarkup", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_id": int(message_id),
                "reply_markup": {"inline_keyboard": []},
            })


def _edit_message_remove_buttons(message_id: str | None, new_suffix: str) -> None:
    """Mantido para compatibilidade."""
    _edit_article_message(message_id, new_suffix, "")


def _edit_caption_remove_buttons(message_id: str | None, new_caption: str) -> None:
    if not message_id:
        return
    with suppress(Exception):
        _tg("editMessageCaption", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(message_id),
            "caption": new_caption,
            "reply_markup": {"inline_keyboard": []},
        })
