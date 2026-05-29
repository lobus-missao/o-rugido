from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import psycopg2
import psycopg2.extras

from .config import DATABASE_URL, ensure_dirs


SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS articles (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        source TEXT NOT NULL,
        source_scope TEXT NOT NULL,
        source_trust NUMERIC NOT NULL DEFAULT 0.5,
        published_at TIMESTAMPTZ,
        summary TEXT,
        content TEXT,
        title_signature TEXT,
        raw_json JSONB,

        auto_score_brasil NUMERIC NOT NULL DEFAULT 0,
        auto_score_piaui NUMERIC NOT NULL DEFAULT 0,
        auto_score_teresina NUMERIC NOT NULL DEFAULT 0,

        final_score_brasil NUMERIC NOT NULL DEFAULT 0,
        final_score_piaui NUMERIC NOT NULL DEFAULT 0,
        final_score_teresina NUMERIC NOT NULL DEFAULT 0,

        ai_score NUMERIC,
        ai_json JSONB,
        category TEXT,
        locality TEXT,
        priority TEXT,
        entities_json JSONB,
        score_reasons_json JSONB,

        card_status TEXT NOT NULL DEFAULT 'none',
        card_path TEXT,
        editorial_status TEXT NOT NULL DEFAULT 'discovered',

        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_canonical_url ON articles(canonical_url)",
    "CREATE INDEX IF NOT EXISTS idx_articles_title_signature ON articles(title_signature)",
    "CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_articles_final_brasil ON articles(final_score_brasil DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_final_piaui ON articles(final_score_piaui DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_final_teresina ON articles(final_score_teresina DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_source_scope ON articles(source_scope)",
    "CREATE INDEX IF NOT EXISTS idx_articles_card_status ON articles(card_status)",
    """
    CREATE TABLE IF NOT EXISTS feed_runs (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        url TEXT NOT NULL,
        status TEXT NOT NULL,
        collected_count INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        started_at TIMESTAMPTZ NOT NULL,
        finished_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_batches (
        batch_id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        status TEXT NOT NULL,
        model TEXT,
        article_count INTEGER NOT NULL DEFAULT 0,
        prompt_path TEXT NOT NULL,
        payload_path TEXT NOT NULL,
        result_path TEXT,
        imported_count INTEGER NOT NULL DEFAULT 0,
        ignored_count INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ai_batches_status ON ai_batches(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ai_batches_scope ON ai_batches(scope, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS dispatches (
        id SERIAL PRIMARY KEY,
        article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        edition TEXT NOT NULL,
        edition_date DATE NOT NULL,
        rank INTEGER NOT NULL,
        scope TEXT NOT NULL DEFAULT 'brasil',
        status TEXT NOT NULL DEFAULT 'pending_article',
        article_tg_message_id TEXT,
        card_tg_message_id TEXT,
        card_path TEXT,
        article_reviewed_by TEXT,
        article_reviewed_at TIMESTAMPTZ,
        card_reviewed_by TEXT,
        card_reviewed_at TIMESTAMPTZ,
        ready_at TIMESTAMPTZ,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dispatches_edition ON dispatches(edition_date, edition)",
    "CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status)",
    "CREATE INDEX IF NOT EXISTS idx_dispatches_article ON dispatches(article_id)",
    """
    CREATE TABLE IF NOT EXISTS sources (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        source_type TEXT NOT NULL DEFAULT 'rss',
        scope TEXT NOT NULL DEFAULT 'brasil',
        trust NUMERIC NOT NULL DEFAULT 0.5,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        last_run_at TIMESTAMPTZ,
        last_status TEXT,
        error_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_name ON sources(name)",
    "CREATE INDEX IF NOT EXISTS idx_sources_scope ON sources(scope)",
    "CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled)",
    """
    CREATE TABLE IF NOT EXISTS editorial_actions (
        id SERIAL PRIMARY KEY,
        article_id TEXT REFERENCES articles(id) ON DELETE SET NULL,
        dispatch_id INTEGER REFERENCES dispatches(id) ON DELETE SET NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL DEFAULT 'system',
        from_status TEXT,
        to_status TEXT,
        notes TEXT,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_editorial_actions_article ON editorial_actions(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_editorial_actions_dispatch ON editorial_actions(dispatch_id)",
    "CREATE INDEX IF NOT EXISTS idx_editorial_actions_created ON editorial_actions(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_editorial_actions_action ON editorial_actions(action)",
]


MIGRATION_SQL = [
    """
    ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'discovered'
    """,
    """
    UPDATE articles SET editorial_status =
        CASE
            WHEN card_status = 'approved' THEN 'approved'
            WHEN card_status = 'rejected' THEN 'rejected'
            WHEN card_status = 'pending' THEN 'sent_to_telegram'
            WHEN ai_score IS NOT NULL AND priority IN ('alta','critica') THEN 'selected'
            WHEN ai_score IS NOT NULL THEN 'ai_done'
            WHEN priority IN ('alta','critica') THEN 'needs_ai'
            ELSE 'discovered'
        END
    WHERE editorial_status IS NULL OR editorial_status = 'discovered'
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_editorial_status ON articles(editorial_status)",
    "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS article_reviewed_by TEXT",
    "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS article_reviewed_at TIMESTAMPTZ",
    "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS card_reviewed_by TEXT",
    "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS card_reviewed_at TIMESTAMPTZ",
    "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS ready_at TIMESTAMPTZ",
]


DATE_COLUMN_MIGRATIONS = {
    "articles": ["published_at", "created_at", "updated_at"],
    "feed_runs": ["started_at", "finished_at"],
    "ai_batches": ["created_at", "started_at", "completed_at", "updated_at"],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def connect() -> Iterator[psycopg2.extensions.connection]:
    ensure_dirs()
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in SCHEMA_SQL:
                cur.execute(statement)
            for statement in MIGRATION_SQL:
                cur.execute(statement)
            _ensure_datetime_columns(cur)


def _ensure_datetime_columns(cur) -> None:
    for table, columns in DATE_COLUMN_MIGRATIONS.items():
        for column in columns:
            cur.execute(
                """
                ALTER TABLE %s
                ALTER COLUMN %s TYPE TIMESTAMPTZ
                USING NULLIF(%s::text, '')::timestamptz
                """ % (table, column, column)
            )


def json_dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value, default=None):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default
