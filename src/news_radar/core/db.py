from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import psycopg2.sql

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

        auto_score_piaui NUMERIC NOT NULL DEFAULT 0,
        final_score_piaui NUMERIC NOT NULL DEFAULT 0,
        coverage_count INTEGER NOT NULL DEFAULT 1,

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
    "CREATE INDEX IF NOT EXISTS idx_articles_final_piaui ON articles(final_score_piaui DESC)",
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


# Migrations versionadas — cada entrada tem chave única.
# init_db() aplica apenas as entradas ainda não registradas em schema_migrations.
# Nunca remover entradas existentes — apenas adicionar novas.
MIGRATION_SQL: dict[str, str] = {
    "v1_editorial_status_column": """
    ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'discovered'
    """,
    "v1_editorial_status_backfill": """
    UPDATE articles SET editorial_status =
        CASE
            WHEN card_status = 'approved' THEN 'approved'
            WHEN card_status = 'rejected' THEN 'rejected'
            WHEN card_status = 'pending' THEN 'sent_to_telegram'
            WHEN priority IN ('alta','critica') THEN 'selected'
            ELSE 'discovered'
        END
    WHERE editorial_status IS NULL OR editorial_status = 'discovered'
    """,
    "v1_editorial_status_index": (
        "CREATE INDEX IF NOT EXISTS idx_articles_editorial_status"
        " ON articles(editorial_status)"
    ),
    "v1_dispatches_reviewed_by": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS article_reviewed_by TEXT"
    ),
    "v1_dispatches_reviewed_at": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS article_reviewed_at TIMESTAMPTZ"
    ),
    "v1_dispatches_card_reviewed_by": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS card_reviewed_by TEXT"
    ),
    "v1_dispatches_card_reviewed_at": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS card_reviewed_at TIMESTAMPTZ"
    ),
    "v1_dispatches_ready_at": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS ready_at TIMESTAMPTZ"
    ),
    # Fase 7
    "v7_articles_card_html_path": (
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS card_html_path TEXT"
    ),
    # Fase 8
    "v8_dispatches_review_notes": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS review_notes TEXT"
    ),
    # Índice full-text para busca em título + resumo (evita ILIKE seq scan)
    "v10_articles_fts_index": (
        "CREATE INDEX IF NOT EXISTS idx_articles_fts "
        "ON articles USING gin(to_tsvector('portuguese', coalesce(title,'') || ' ' || coalesce(summary,'')))"
    ),
    # Índice composto para order by score + data (evita sort em memória)
    "v10_articles_score_date_piaui": (
        "CREATE INDEX IF NOT EXISTS idx_articles_score_date_piaui "
        "ON articles(final_score_piaui DESC, published_at DESC NULLS LAST)"
    ),
    # v11 — escopo único (Piauí). Remove colunas/índices Brasil e Teresina.
    "v11_drop_brasil_score_indexes": (
        "DROP INDEX IF EXISTS idx_articles_final_brasil; "
        "DROP INDEX IF EXISTS idx_articles_final_teresina; "
        "DROP INDEX IF EXISTS idx_articles_score_date_brasil; "
        "DROP INDEX IF EXISTS idx_articles_score_date_teresina;"
    ),
    "v11_drop_brasil_score_columns": (
        "ALTER TABLE articles DROP COLUMN IF EXISTS auto_score_brasil; "
        "ALTER TABLE articles DROP COLUMN IF EXISTS auto_score_teresina; "
        "ALTER TABLE articles DROP COLUMN IF EXISTS final_score_brasil; "
        "ALTER TABLE articles DROP COLUMN IF EXISTS final_score_teresina;"
    ),
    # v12 — remove tabelas de features cortadas (IA, clusters, scraping).
    # Em DBs novos as tabelas nunca existiram; em DBs existentes são dropadas aqui.
    "v12_drop_legacy_tables": (
        "DROP TABLE IF EXISTS scraped_pages CASCADE; "
        "DROP TABLE IF EXISTS scrape_runs CASCADE; "
        "DROP TABLE IF EXISTS source_rules CASCADE; "
        "DROP TABLE IF EXISTS cluster_articles CASCADE; "
        "DROP TABLE IF EXISTS story_clusters CASCADE; "
        "DROP TABLE IF EXISTS ai_batches CASCADE;"
    ),
    # v13 — edição via web (token + overrides por dispatch)
    "v13_dispatches_edit_token": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS edit_token TEXT"
    ),
    "v13_dispatches_edit_token_expires_at": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS edit_token_expires_at TIMESTAMPTZ"
    ),
    "v13_dispatches_edited_title": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS edited_title TEXT"
    ),
    "v13_dispatches_edited_summary": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS edited_summary TEXT"
    ),
    "v13_dispatches_image_url": (
        "ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS image_url TEXT"
    ),
    "v13_dispatches_edit_token_idx": (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dispatches_edit_token"
        " ON dispatches(edit_token) WHERE edit_token IS NOT NULL"
    ),
    # v14 — remove camada IA (nunca foi conectada na prática).
    "v14_articles_drop_ai_columns": (
        "ALTER TABLE articles DROP COLUMN IF EXISTS ai_score; "
        "ALTER TABLE articles DROP COLUMN IF EXISTS ai_json;"
    ),
    # v15 — cobertura por múltiplas fontes (sinal de exclusividade/destaque).
    "v15_articles_coverage_count": (
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS coverage_count INTEGER NOT NULL DEFAULT 1"
    ),
    "v15_articles_coverage_count_idx": (
        "CREATE INDEX IF NOT EXISTS idx_articles_coverage_count ON articles(coverage_count DESC)"
    ),
}

DATE_COLUMN_MIGRATIONS = {
    "articles": ["published_at", "created_at", "updated_at"],
    "feed_runs": ["started_at", "finished_at"],
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
    with connect() as conn, conn.cursor() as cur:
        for statement in SCHEMA_SQL:
            cur.execute(statement)

        # Tabela de controle de versão de migrations (Fase 9)
        cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

        # Aplica apenas migrations ainda não registradas
        cur.execute("SELECT id FROM schema_migrations")
        applied = {row["id"] for row in cur.fetchall()}
        for migration_id, stmt in MIGRATION_SQL.items():
            if migration_id not in applied:
                cur.execute(stmt)
                cur.execute(
                    "INSERT INTO schema_migrations (id, applied_at) VALUES (%s, NOW())",
                    (migration_id,),
                )

        _ensure_datetime_columns(cur)


def _ensure_datetime_columns(cur) -> None:
    """Converte colunas de data para TIMESTAMPTZ apenas se ainda não forem TIMESTAMPTZ."""
    for table, columns in DATE_COLUMN_MIGRATIONS.items():
        for column in columns:
            # Verifica o tipo atual antes de alterar (evita ALTER desnecessário)
            cur.execute(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name   = %s
                  AND column_name  = %s
                """,
                (table, column),
            )
            row = cur.fetchone()
            if row and row["data_type"] != "timestamp with time zone":
                # Usa psycopg2.sql para escapar identificadores — evita SQL injection
                cur.execute(
                    psycopg2.sql.SQL(
                        "ALTER TABLE {t} ALTER COLUMN {c} TYPE TIMESTAMPTZ"
                        " USING NULLIF({c}::text, '')::timestamptz"
                    ).format(
                        t=psycopg2.sql.Identifier(table),
                        c=psycopg2.sql.Identifier(column),
                    )
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
