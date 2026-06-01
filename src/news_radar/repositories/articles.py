from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from news_radar.core.db import connect

Scope = Literal["piaui"]

SCORE_COLUMN = {
    "piaui": "final_score_piaui",
}


def top_articles(
    scope: Scope = "piaui",
    limit: int = 30,
    only_with_score: bool = True,
    days_back: int | None = None,
    search: str | None = None,
    priority: list[str] | None = None,
) -> list[dict]:
    column = SCORE_COLUMN[scope]
    conditions = []
    params: list = []

    if only_with_score:
        conditions.append(f"{column} > 0")

    if days_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        conditions.append("(published_at >= %s OR published_at IS NULL)")
        params.append(cutoff)

    if search:
        conditions.append("(title ILIKE %s OR summary ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if priority:
        placeholders = ",".join(["%s"] * len(priority))
        conditions.append(f"priority IN ({placeholders})")
        params.extend(priority)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM articles
                {where}
                ORDER BY {column} DESC, published_at DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]


def recent_articles(limit: int = 100) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM articles
                ORDER BY COALESCE(published_at, created_at) DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def articles_pending_card(scope: Scope = "piaui", limit: int = 5) -> list[dict]:
    column = SCORE_COLUMN[scope]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM articles
                WHERE priority IN ('alta', 'critica')
                  AND card_status = 'none'
                  AND {column} > 0
                ORDER BY {column} DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def update_card_status(
    article_id: str,
    status: str,
    card_path: str | None = None,
    html_path: str | None = None,
) -> None:
    from news_radar.core.db import utc_now
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE articles
                SET card_status = %s,
                    card_path = COALESCE(%s, card_path),
                    card_html_path = COALESCE(%s, card_html_path),
                    updated_at = %s
                WHERE id = %s
                """,
                (status, card_path, html_path, utc_now(), article_id),
            )


def stats() -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM articles")
            total = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) AS total FROM articles WHERE ai_score IS NOT NULL")
            with_ai = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM ai_batches
                GROUP BY status
                """
            )
            batch_totals = cur.fetchall()

            cur.execute(
                """
                SELECT source, status, collected_count, error, finished_at
                FROM feed_runs
                ORDER BY id DESC
                LIMIT 30
                """
            )
            feed_runs = cur.fetchall()

    return {
        "total_articles": total,
        "articles_with_ai": with_ai,
        "ai_batches": {row["status"]: row["total"] for row in batch_totals},
        "feed_runs": [dict(row) for row in feed_runs],
    }
