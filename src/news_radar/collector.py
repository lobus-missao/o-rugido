from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
from dateutil import parser as date_parser

from .config import load_feeds_config
from .db import connect, init_db, json_dumps, utc_now
from .ranker import automatic_scores
from .text_utils import article_id, canonicalize_url, strip_html, title_signature


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
        "source_scope": source.get("scope", "brasil"),
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
                    auto_score_brasil = %s,
                    auto_score_piaui = %s,
                    auto_score_teresina = %s,
                    final_score_brasil = CASE
                        WHEN ai_score IS NULL THEN %s
                        ELSE final_score_brasil
                    END,
                    final_score_piaui = CASE
                        WHEN ai_score IS NULL THEN %s
                        ELSE final_score_piaui
                    END,
                    final_score_teresina = CASE
                        WHEN ai_score IS NULL THEN %s
                        ELSE final_score_teresina
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
                    item["auto_score_brasil"],
                    item["auto_score_piaui"],
                    item["auto_score_teresina"],
                    item["final_score_brasil"],
                    item["final_score_piaui"],
                    item["final_score_teresina"],
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
                auto_score_brasil, auto_score_piaui, auto_score_teresina,
                final_score_brasil, final_score_piaui, final_score_teresina,
                score_reasons_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                item["auto_score_brasil"],
                item["auto_score_piaui"],
                item["auto_score_teresina"],
                item["final_score_brasil"],
                item["final_score_piaui"],
                item["final_score_teresina"],
                json_dumps(item.get("reasons", [])),
                now,
                now,
            ),
        )
        return cur.rowcount > 0


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
                    item = normalize_entry(entry, source)
                    if not item:
                        continue
                    inserted = upsert_article(conn, item)
                    collected += 1
                    if inserted:
                        result["inserted"] += 1
                    else:
                        result["updated"] += 1

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

    return result
