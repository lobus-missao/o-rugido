"""
Repositório de fontes RSS/API/scraping.
Fase 2 — gerenciamento de fontes via banco, coexistindo com feeds.yaml.
"""
from __future__ import annotations

from news_radar.core.db import connect, utc_now


def list_sources(
    scope: str | None = None,
    enabled_only: bool = False,
) -> list[dict]:
    """Lista fontes ordenadas por escopo e nome, com filtros opcionais."""
    conditions: list[str] = []
    params: list = []
    if scope:
        conditions.append("scope = %s")
        params.append(scope)
    if enabled_only:
        conditions.append("enabled = TRUE")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM sources {where} ORDER BY scope, name",
            params,
        )
        return [dict(row) for row in cur.fetchall()]


def get_source_by_name(name: str) -> dict | None:
    """Retorna fonte pelo nome ou None se não encontrada."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM sources WHERE name = %s", (name,))
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_source(
    name: str,
    url: str,
    source_type: str = "rss",
    scope: str = "piaui",
    trust: float = 0.5,
    enabled: bool = True,
) -> dict:
    """Cria ou atualiza fonte por name (unique). Retorna o registro final.

    Idempotente: chamadas repetidas com o mesmo name apenas atualizam os campos.
    """
    now = utc_now()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (name, url, source_type, scope, trust, enabled, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                url         = EXCLUDED.url,
                source_type = EXCLUDED.source_type,
                scope       = EXCLUDED.scope,
                trust       = EXCLUDED.trust,
                enabled     = EXCLUDED.enabled,
                updated_at  = EXCLUDED.updated_at
            RETURNING *
            """,
            (name, url, source_type, scope, trust, enabled, now, now),
        )
        return dict(cur.fetchone())


def mark_source_success(source_id: int, collected_count: int = 0) -> None:
    """Registra coleta bem-sucedida: last_status='ok', error_count=0."""
    now = utc_now()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
                UPDATE sources
                SET last_run_at = %s,
                    last_status = 'ok',
                    error_count = 0,
                    updated_at  = %s
                WHERE id = %s
                """,
            (now, now, source_id),
        )


def mark_source_error(source_id: int, error_msg: str) -> None:
    """Registra erro de coleta: incrementa error_count, last_status='error'."""
    now = utc_now()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
                UPDATE sources
                SET last_run_at = %s,
                    last_status = 'error',
                    error_count = error_count + 1,
                    updated_at  = %s
                WHERE id = %s
                """,
            (now, now, source_id),
        )
