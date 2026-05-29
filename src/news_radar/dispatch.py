"""
Controle editorial de edições (morning/noon/evening).
Gerencia o fluxo: selecionar top 3 → aprovar artigo → gerar card → aprovar card.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

_logger = logging.getLogger(__name__)

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from .db import connect, utc_now

EDITIONS = {
    "morning": {"label": "Manhã (7h)",    "dispatch_hour": 6,  "dispatch_min": 30, "post_hour": 7},
    "noon":    {"label": "Meio-dia (12h)", "dispatch_hour": 11, "dispatch_min": 30, "post_hour": 12},
    "evening": {"label": "Tarde (18h)",   "dispatch_hour": 17, "dispatch_min": 30, "post_hour": 18},
}

# Janelas de coleta por edição (horas atrás do horário de disparo)
EDITION_WINDOWS = {
    "morning": 13,  # 6:30am → busca das últimas 13h (desde 17:30 dia anterior)
    "noon":    5,   # 11:30am → busca das últimas 5h (desde 6:30am)
    "evening": 6,   # 5:30pm → busca das últimas 6h (desde 11:30am)
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


def get_dispatch(dispatch_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dispatches WHERE id = %s", (dispatch_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def update_dispatch(dispatch_id: int, **fields) -> None:
    fields["updated_at"] = utc_now()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [dispatch_id]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE dispatches SET {set_clause} WHERE id = %s", values)


def get_edition_dispatches(edition: str, edition_date: date) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.*, a.title, a.source, a.summary, a.final_score_brasil,
                       a.final_score_piaui, a.final_score_teresina,
                       a.priority, a.ai_json, a.card_path, a.canonical_url, a.published_at
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


def select_top_articles(edition: str, scope: str = "brasil", top: int = 3) -> list[dict]:
    """Seleciona os melhores artigos para a edição, excluindo já despachados hoje."""
    window_hours = EDITION_WINDOWS.get(edition, 6)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    score_col = f"final_score_{scope}"
    today = date.today()

    with connect() as conn:
        with conn.cursor() as cur:
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

    # Remove já despachados, pega os top N
    selected = [a for a in candidates if a["id"] not in already][:top]
    return selected


def create_dispatch(
    edition: str,
    scope: str = "brasil",
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
    with connect() as conn:
        with conn.cursor() as cur:
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

    with connect() as conn:
        with conn.cursor() as cur:
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
    ai_json = art.get("ai_json") or {}
    if isinstance(ai_json, str):
        try:
            ai_json = json.loads(ai_json)
        except Exception:
            ai_json = {}

    score = float(art.get("final_score_brasil") or 0)
    priority = (art.get("priority") or "-").upper()
    resumo = ai_json.get("resumo_curto") or (art.get("summary") or "")[:200]
    pontos = ai_json.get("pontos_chave") or []
    pontos_txt = "\n".join(f"• {p}" for p in pontos[:3])
    source = art.get("source") or ""
    pub = str(art.get("published_at") or "")[:16]

    text = (
        f"#{rank} de 3 · Score {score:.0f} · *{priority}*\n\n"
        f"*{art.get('title','')[:120]}*\n\n"
        f"{pontos_txt}\n\n"
        f"_Fonte: {source} · {pub}_"
    )

    result = _tg("sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Aprovar",  "callback_data": f"dispatch_approve:{dispatch_id}"},
                {"text": "❌ Rejeitar", "callback_data": f"dispatch_reject:{dispatch_id}"},
            ]]
        },
    })
    msg_id = str(result.get("result", {}).get("message_id", ""))
    update_dispatch(dispatch_id, article_tg_message_id=msg_id)


def approve_article(
    dispatch_id: int,
    user: str = "Editor",
    *,
    generate_card: bool = True,
    dry_run: bool | None = None,
) -> dict:
    """Editor aprovou o artigo. Por compatibilidade, gera o card por padrão."""
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    # Bloqueia double-processing
    if dispatch["status"] not in ("pending_article",):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    update_dispatch(
        dispatch_id,
        status="article_approved",
        article_reviewed_by=user,
        article_reviewed_at=utc_now(),
    )

    # Edita a mensagem original em-lugar mostrando aprovação
    _edit_article_message(
        dispatch.get("article_tg_message_id"),
        status_text="✅ APROVADO",
        user=user,
    )

    if not generate_card:
        return {"ok": True, "dispatch_id": dispatch_id, "status": "article_approved"}

    return generate_card_for_dispatch(dispatch_id, user=user, dry_run=dry_run)


def generate_card_for_dispatch(
    dispatch_id: int,
    user: str = "Editor",
    *,
    dry_run: bool | None = None,
) -> dict:
    from .card_renderer import render_cards

    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}
    if dispatch["status"] not in ("article_approved", "pending_card", "card_rejected"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    # Gera o card imediatamente
    scope = dispatch.get("scope", "brasil")
    card_path = None
    error_msg = None
    try:
        cards = render_cards(scope=scope, limit=1, article_ids=[dispatch["article_id"]])
        card_path = cards[0]["card_path"] if cards else None
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
        msg = f"⚠️ Artigo aprovado! Card não gerado automaticamente."
        if error_msg:
            msg += f"\nErro: `{error_msg}`"
        msg += f"\nDispatch ID: `{dispatch_id}` — gere pelo dashboard."
        _tg("sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        })
        return {"ok": False, "dispatch_id": dispatch_id, "status": dispatch["status"], "error": error_msg}


def reject_article(dispatch_id: int, user: str = "Editor") -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    # Bloqueia double-processing
    if dispatch["status"] not in ("pending_article",):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    update_dispatch(
        dispatch_id,
        status="article_rejected",
        article_reviewed_by=user,
        article_reviewed_at=utc_now(),
    )
    _edit_article_message(
        dispatch.get("article_tg_message_id"),
        status_text="❌ REJEITADO",
        user=user,
    )
    return {"ok": True, "dispatch_id": dispatch_id, "status": "article_rejected"}


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

    with open(card_path, "rb") as photo:
        result = _tg("sendPhoto", data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": f"🖼️ *Card gerado*\n\nAprove para publicar ou rejeite.\n_(Aprovado o artigo por {user})_",
            "parse_mode": "Markdown",
            "reply_markup": json.dumps({"inline_keyboard": [[
                {"text": "✅ Publicar",    "callback_data": f"card_approve:{dispatch_id}"},
                {"text": "🔄 Regerar",     "callback_data": f"card_regenerate:{dispatch_id}"},
                {"text": "❌ Rejeitar",    "callback_data": f"card_reject:{dispatch_id}"},
            ]]}),
        }, files={"photo": photo})
    msg_id = str(result.get("result", {}).get("message_id", ""))
    update_dispatch(dispatch_id, card_tg_message_id=msg_id)


def approve_card(dispatch_id: int, user: str = "Editor") -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}
    if dispatch["status"] not in ("pending_card", "card_approved", "ready_to_publish"):
        return {"ok": True, "skipped": True, "dispatch_id": dispatch_id, "status": dispatch["status"]}

    now = utc_now()
    update_dispatch(
        dispatch_id,
        status="ready_to_publish",
        card_reviewed_by=user,
        card_reviewed_at=now,
        ready_at=now,
    )
    _edit_caption_remove_buttons(
        dispatch.get("card_tg_message_id"),
        f"✅ APROVADO para publicação por {user}"
    )
    # Atualiza editorial_status do artigo
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE articles SET editorial_status='ready_to_publish', card_status='approved', updated_at=NOW() WHERE id=%s",
                (dispatch["article_id"],)
            )
    return {"ok": True, "dispatch_id": dispatch_id, "status": "ready_to_publish"}


def reject_card(dispatch_id: int, user: str = "Editor") -> dict:
    dispatch = get_dispatch(dispatch_id)
    if not dispatch:
        return {"ok": False, "error": "dispatch nao encontrado", "dispatch_id": dispatch_id}

    update_dispatch(
        dispatch_id,
        status="card_rejected",
        card_reviewed_by=user,
        card_reviewed_at=utc_now(),
    )
    _edit_caption_remove_buttons(
        dispatch.get("card_tg_message_id"),
        f"❌ CARD REJEITADO por {user}"
    )
    with connect() as conn:
        with conn.cursor() as cur:
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


def mark_published(dispatch_id: int) -> None:
    dispatch = get_dispatch(dispatch_id)
    if dispatch:
        update_dispatch(dispatch_id, status="published")
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET editorial_status='published', updated_at=NOW() WHERE id=%s",
                    (dispatch["article_id"],)
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
    """Edita a mensagem do artigo em-lugar: adiciona status no topo e remove botões."""
    if not message_id:
        return
    try:
        # Primeiro tenta editar o texto da mensagem adicionando o status
        _tg("editMessageText", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(message_id),
            "text": f"{status_text} por *{user}*",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception:
        # Fallback: só remove os botões
        try:
            _tg("editMessageReplyMarkup", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_id": int(message_id),
                "reply_markup": {"inline_keyboard": []},
            })
        except Exception:
            pass


def _edit_message_remove_buttons(message_id: str | None, new_suffix: str) -> None:
    """Mantido para compatibilidade."""
    _edit_article_message(message_id, new_suffix, "")


def _edit_caption_remove_buttons(message_id: str | None, new_caption: str) -> None:
    if not message_id:
        return
    try:
        _tg("editMessageCaption", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(message_id),
            "caption": new_caption,
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception:
        pass
