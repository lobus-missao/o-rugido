"""CRUD de source_rules."""
from __future__ import annotations
from typing import Any

from ..db import connect, json_dumps


def list_source_rules(
    enabled: bool | None = None,
    strategy: str | None = None,
    source_id: int | None = None,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if enabled is not None:
        clauses.append("sr.enabled = %s")
        params.append(enabled)
    if strategy:
        clauses.append("sr.strategy = %s")
        params.append(strategy)
    if source_id is not None:
        clauses.append("sr.source_id = %s")
        params.append(source_id)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT sr.*, s.name AS source_name, s.scope AS source_scope, s.url AS source_url
        FROM source_rules sr
        LEFT JOIN sources s ON sr.source_id = s.id
        {where}
        ORDER BY sr.id
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def get_source_rule(rule_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sr.*, s.name AS source_name, s.scope AS source_scope
                FROM source_rules sr
                LEFT JOIN sources s ON sr.source_id = s.id
                WHERE sr.id = %s
                """,
                (rule_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_rule_for_source(source_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM source_rules WHERE source_id = %s ORDER BY id LIMIT 1",
                (source_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def upsert_source_rule(
    source_id: int,
    strategy: str = "trafilatura",
    list_url: str | None = None,
    article_url_pattern: str | None = None,
    title_selector: str | None = None,
    content_selector: str | None = None,
    date_selector: str | None = None,
    author_selector: str | None = None,
    image_selector: str | None = None,
    enabled: bool = False,
    rate_limit_seconds: float = 2.0,
    timeout_seconds: int = 30,
    config_json: dict | None = None,
    rule_id: int | None = None,
) -> int:
    """Cria ou atualiza uma source_rule. Retorna o id."""
    cfg = json_dumps(config_json)
    with connect() as conn:
        with conn.cursor() as cur:
            if rule_id:
                cur.execute(
                    """
                    UPDATE source_rules SET
                        source_id=%s, strategy=%s, list_url=%s,
                        article_url_pattern=%s, title_selector=%s, content_selector=%s,
                        date_selector=%s, author_selector=%s, image_selector=%s,
                        enabled=%s, rate_limit_seconds=%s, timeout_seconds=%s,
                        config_json=%s, updated_at=NOW()
                    WHERE id=%s
                    RETURNING id
                    """,
                    (
                        source_id, strategy, list_url,
                        article_url_pattern, title_selector, content_selector,
                        date_selector, author_selector, image_selector,
                        enabled, rate_limit_seconds, timeout_seconds,
                        cfg, rule_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO source_rules (
                        source_id, strategy, list_url, article_url_pattern,
                        title_selector, content_selector, date_selector,
                        author_selector, image_selector, enabled,
                        rate_limit_seconds, timeout_seconds, config_json
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        source_id, strategy, list_url,
                        article_url_pattern, title_selector, content_selector,
                        date_selector, author_selector, image_selector,
                        enabled, rate_limit_seconds, timeout_seconds, cfg,
                    ),
                )
            row = cur.fetchone()
            return row["id"] if row else -1
