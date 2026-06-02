from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from news_radar.core.cache import ttl_cache
from news_radar.core.db import connect, utc_now


@ttl_cache(seconds=60)
def pipeline_health() -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM articles")
        total_articles = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM articles WHERE priority IS NOT NULL")
        classified = cur.fetchone()["n"]

        cur.execute(
            "SELECT MAX(finished_at) AS last FROM feed_runs WHERE status = 'ok'"
        )
        last_ok = cur.fetchone()["last"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM feed_runs "
            "WHERE status = 'error' AND finished_at > NOW() - INTERVAL '24 hours'"
        )
        errors_24h = cur.fetchone()["n"]

    return {
        "total_articles": int(total_articles or 0),
        "classified": int(classified or 0),
        "last_collect_ok": last_ok,
        "errors_24h": int(errors_24h or 0),
    }


@ttl_cache(seconds=60)
def sources_summary() -> dict[str, Any]:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT "
                "COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE enabled) AS enabled, "
                "COUNT(*) FILTER (WHERE last_status = 'error') AS with_error "
                "FROM sources"
            )
            row = cur.fetchone() or {}
    except Exception:
        return {"total": 0, "enabled": 0, "with_error": 0, "by_scope": {}}

    return {
        "total": int(row.get("total") or 0),
        "enabled": int(row.get("enabled") or 0),
        "with_error": int(row.get("with_error") or 0),
        "by_scope": {},
    }


@ttl_cache(seconds=60)
def daily_article_activity(days: int = 14) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DATE(published_at) AS date, COUNT(*) AS count "
            "FROM articles "
            "WHERE published_at >= %s "
            "GROUP BY DATE(published_at) "
            "ORDER BY date",
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


@ttl_cache(seconds=30)
def recent_editorial_actions(limit: int = 20) -> list[dict[str, Any]]:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT action, actor, article_id, dispatch_id, "
                "from_status, to_status, notes, created_at "
                "FROM editorial_actions "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def dispatch_audit_history(dispatch_id: int) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT action, actor, from_status, to_status, notes, created_at "
            "FROM editorial_actions "
            "WHERE dispatch_id = %s "
            "ORDER BY created_at",
            (dispatch_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def update_editorial_status(article_id: str, status: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE articles SET editorial_status = %s, updated_at = %s WHERE id = %s",
            (status, utc_now(), article_id),
        )
