"""CRUD de scrape_runs e scraped_pages."""
from __future__ import annotations
from typing import Any

from ..db import connect, json_dumps
from .models import ScrapeRunStats


def get_known_urls(source_id: int | None = None) -> set[str]:
    """
    Retorna conjunto de URLs já conhecidas para um portal:
    - scraped_pages (tentativas anteriores, com ou sem erro)
    - articles (já entraram no pipeline editorial via canonical_url)

    Usado pelos scrapers para pular URLs já processadas.
    """
    known: set[str] = set()
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                # URLs em scraped_pages para esta fonte
                if source_id is not None:
                    cur.execute(
                        "SELECT url FROM scraped_pages WHERE source_id = %s",
                        (source_id,),
                    )
                else:
                    cur.execute("SELECT url FROM scraped_pages")
                known.update(row["url"] for row in cur.fetchall())

                # URLs já em articles (canonical_url)
                cur.execute("SELECT canonical_url FROM articles")
                known.update(row["canonical_url"] for row in cur.fetchall())
    except Exception:
        pass  # sem banco: retorna conjunto vazio, scraper opera normalmente
    return known


def create_scrape_run(source_id: int | None, strategy: str) -> int:
    """Cria um scrape_run com status='running'. Retorna o id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scrape_runs (source_id, strategy, status, started_at)
                VALUES (%s, %s, 'running', NOW())
                RETURNING id
                """,
                (source_id, strategy),
            )
            return cur.fetchone()["id"]


def finish_scrape_run(
    run_id: int,
    stats: ScrapeRunStats,
    metadata: dict | None = None,
) -> None:
    """Encerra um scrape_run com contagens e status final."""
    status = "error" if stats.errors > 0 and stats.found == 0 else "ok"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs SET
                    status = %s,
                    finished_at = NOW(),
                    found_count = %s,
                    inserted_count = %s,
                    updated_count = %s,
                    skipped_count = %s,
                    error_count = %s,
                    error_message = %s,
                    metadata_json = %s
                WHERE id = %s
                """,
                (
                    status,
                    stats.found,
                    stats.inserted,
                    stats.updated,
                    stats.skipped,
                    stats.errors,
                    (stats.error_message or "")[:500] if stats.error_message else None,
                    json_dumps(metadata),
                    run_id,
                ),
            )


def list_scrape_runs(
    source_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if source_id is not None:
        clauses.append("sr.source_id = %s")
        params.append(source_id)
    if status:
        clauses.append("sr.status = %s")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    sql = f"""
        SELECT sr.*, s.name AS source_name
        FROM scrape_runs sr
        LEFT JOIN sources s ON sr.source_id = s.id
        {where}
        ORDER BY sr.started_at DESC
        LIMIT %s
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def insert_scraped_page(
    source_id: int | None,
    run_id: int | None,
    url: str,
    status_code: int | None = None,
    content_hash: str | None = None,
    extraction_status: str = "ok",
    title: str | None = None,
    published_at=None,
    error_message: str | None = None,
) -> int:
    """Registra uma scraped_page. Retorna o id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scraped_pages (
                    source_id, run_id, url, status_code, content_hash,
                    extraction_status, title, published_at, error_message, fetched_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                RETURNING id
                """,
                (
                    source_id, run_id, url, status_code, content_hash,
                    extraction_status,
                    (title or "")[:500] if title else None,
                    published_at,
                    (error_message or "")[:500] if error_message else None,
                ),
            )
            row = cur.fetchone()
            return row["id"] if row else -1
