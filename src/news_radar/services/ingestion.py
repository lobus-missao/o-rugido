from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

import feedparser
from dateutil import parser as date_parser

from news_radar.adapters.n8n_webhook import notify_ingestion_complete
from news_radar.core.db import connect, init_db, json_dumps, utc_now
from news_radar.core.text_utils import article_id, canonicalize_url, strip_html, title_signature

from .feeds import load_feeds_config
from .ranker import automatic_scores

_logger = logging.getLogger(__name__)


def entry_published_at(entry: Any) -> datetime | None:
    candidates = [
        getattr(entry, "published", None),
        getattr(entry, "updated", None),
        getattr(entry, "created", None),
    ]
    for value in candidates:
        if not value:
            continue
        try:
            return date_parser.parse(value).astimezone(timezone.utc)
        except Exception:
            continue
    return None


def entry_summary(entry: Any) -> str:
    summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
    return strip_html(summary)


def normalize_entry(entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
    title = strip_html(getattr(entry, "title", "") or "")
    url = getattr(entry, "link", "") or ""

    if not title or not url:
        return None

    canonical_url = canonicalize_url(url)
    summary = entry_summary(entry)
    published_at = entry_published_at(entry)
    raw_json = {}
    try:
        raw_json = dict(entry)
    except Exception:
        raw_json = {"repr": repr(entry)}

    item = {
        "id": article_id(canonical_url, title),
        "title": title,
        "url": url,
        "canonical_url": canonical_url,
        "source": source["name"],
        "source_scope": source.get("scope", "piaui"),
        "source_trust": float(source.get("trust", 0.5) or 0.5),
        "published_at": published_at,
        "summary": summary,
        "content": summary,
        "title_signature": title_signature(title),
        "raw_json": json_dumps(raw_json),
    }

    scores = automatic_scores(item)
    item.update(scores)
    return item


def upsert_article(conn, item: dict[str, Any]) -> bool:
    now = utc_now()

    with conn.cursor() as cur:
        # Prefer URL matches. Title signatures are fuzzy and may collide across
        # syndicated stories that already have a different canonical URL.
        cur.execute("SELECT id FROM articles WHERE canonical_url = %s LIMIT 1", (item["canonical_url"],))
        existing = cur.fetchone()
        if not existing:
            cur.execute("SELECT id FROM articles WHERE title_signature = %s LIMIT 1", (item["title_signature"],))
            existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE articles SET
                    title = %s,
                    url = %s,
                    canonical_url = %s,
                    source = %s,
                    source_scope = %s,
                    source_trust = %s,
                    published_at = COALESCE(%s, published_at),
                    summary = %s,
                    content = %s,
                    raw_json = %s,
                    auto_score_piaui = %s,
                    final_score_piaui = CASE
                        WHEN ai_score IS NULL THEN %s
                        ELSE final_score_piaui
                    END,
                    score_reasons_json = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    item["title"],
                    item["url"],
                    item["canonical_url"],
                    item["source"],
                    item["source_scope"],
                    item["source_trust"],
                    item["published_at"],
                    item["summary"],
                    item["content"],
                    item["raw_json"],
                    item["auto_score_piaui"],
                    item["final_score_piaui"],
                    json_dumps(item.get("reasons", [])),
                    now,
                    existing["id"],
                ),
            )
            return False

        cur.execute(
            """
            INSERT INTO articles (
                id, title, url, canonical_url, source, source_scope, source_trust,
                published_at, summary, content, title_signature, raw_json,
                auto_score_piaui, final_score_piaui,
                score_reasons_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                item["id"],
                item["title"],
                item["url"],
                item["canonical_url"],
                item["source"],
                item["source_scope"],
                item["source_trust"],
                item["published_at"],
                item["summary"],
                item["content"],
                item["title_signature"],
                item["raw_json"],
                item["auto_score_piaui"],
                item["final_score_piaui"],
                json_dumps(item.get("reasons", [])),
                now,
                now,
            ),
        )
        return cur.rowcount > 0


def _try_update_source_status(
    source_name: str,
    status: str,
    collected: int,
    error: str | None,
) -> None:
    """Atualiza status de monitoramento na tabela sources (best-effort).

    Não quebra a coleta se a tabela não existir ou a fonte não estiver cadastrada.
    """
    try:
        from news_radar.repositories.sources import (
            get_source_by_name,
            mark_source_error,
            mark_source_success,
        )

        src = get_source_by_name(source_name)
        if src is None:
            return  # Fonte ainda não está na tabela sources — feeds.yaml ativo
        if status in ("ok", "warning"):
            mark_source_success(src["id"], collected_count=collected)
        else:
            mark_source_error(src["id"], error_msg=(error or status)[:500])
    except Exception as exc:
        _logger.warning(
            "Falha ao atualizar status da fonte '%s' em sources: %s",
            source_name,
            str(exc)[:120],
        )


def collect_feeds(limit_per_feed: int = 30) -> dict[str, Any]:
    init_db()
    config = load_feeds_config()
    feeds = [f for f in config.get("feeds", []) if f.get("enabled", True)]

    result = {
        "feeds_total": len(feeds),
        "inserted": 0,
        "updated": 0,
        "errors": [],
    }

    with connect() as conn:
        for source in feeds:
            started_at = utc_now()
            collected = 0
            status = "ok"
            error = None

            try:
                parsed = feedparser.parse(source["url"])
                entries = parsed.entries[:limit_per_feed] if limit_per_feed else parsed.entries

                for entry in entries:
                    try:
                        item = normalize_entry(entry, source)
                        if not item:
                            continue
                        was_inserted = upsert_article(conn, item)
                        collected += 1
                        if was_inserted:
                            result["inserted"] += 1
                        else:
                            result["updated"] += 1
                    except Exception as entry_exc:
                        _logger.warning(
                            "Erro ao processar entry '%s' de '%s': %s",
                            getattr(entry, "title", "?")[:80],
                            source.get("name", "?"),
                            str(entry_exc)[:200],
                        )
                        result["errors"].append({
                            "source": source.get("name"),
                            "entry": getattr(entry, "title", "?")[:80],
                            "error": str(entry_exc)[:200],
                        })

                if getattr(parsed, "bozo", False):
                    bozo_exception = getattr(parsed, "bozo_exception", None)
                    if bozo_exception:
                        status = "warning"
                        error = str(bozo_exception)[:500]

            except Exception as exc:
                status = "error"
                error = f"{exc}\n{traceback.format_exc(limit=2)}"
                result["errors"].append({"source": source.get("name"), "error": str(exc)})
                conn.rollback()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feed_runs (source, url, status, collected_count, error, started_at, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source.get("name"),
                        source.get("url"),
                        status,
                        collected,
                        error,
                        started_at,
                        utc_now(),
                    ),
                )

            _try_update_source_status(source.get("name", ""), status, collected, error)

    notify_ingestion_complete({
        "feeds_total": result["feeds_total"],
        "inserted": result["inserted"],
        "updated": result["updated"],
        "errors_count": len(result["errors"]),
    })

    return result
