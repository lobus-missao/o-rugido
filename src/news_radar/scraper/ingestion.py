"""
Fase 10.2 — Ingestão: scraped_pages → articles.

Transforma páginas extraídas com sucesso em artigos do pipeline editorial,
reutilizando a mesma lógica de normalização, deduplicação e scoring do RSS.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

from ..collector import upsert_article
from ..db import connect, json_dumps, utc_now
from ..ranker import automatic_scores
from ..text_utils import article_id, canonicalize_url, strip_html, title_signature

_logger = logging.getLogger(__name__)


# ── Consulta de elegibilidade ─────────────────────────────────────────────────

def get_eligible_pages(
    source_id: int | None = None,
    run_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Retorna scraped_pages elegíveis para ingestão:
    - extraction_status = 'ok'
    - ingestion_status = 'pending'
    - title não vazio
    - url não vazio
    """
    clauses = [
        "sp.extraction_status = 'ok'",
        "sp.ingestion_status = 'pending'",
        "sp.title IS NOT NULL AND sp.title <> ''",
        "sp.url IS NOT NULL AND sp.url <> ''",
    ]
    params: list[Any] = []

    if source_id is not None:
        clauses.append("sp.source_id = %s")
        params.append(source_id)
    if run_id is not None:
        clauses.append("sp.run_id = %s")
        params.append(run_id)

    params.append(limit)
    sql = f"""
        SELECT sp.*, s.name AS source_name, s.scope AS source_scope,
               s.trust AS source_trust
        FROM scraped_pages sp
        LEFT JOIN sources s ON sp.source_id = s.id
        WHERE {" AND ".join(clauses)}
        ORDER BY sp.fetched_at DESC
        LIMIT %s
    """
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        _logger.error("Erro ao consultar páginas elegíveis: %s", str(exc)[:200])
        return []


def count_eligible_pages(
    source_id: int | None = None,
    run_id: int | None = None,
) -> int:
    """Contagem rápida de páginas elegíveis para ingestão."""
    clauses = [
        "extraction_status = 'ok'",
        "ingestion_status = 'pending'",
        "title IS NOT NULL AND title <> ''",
        "url IS NOT NULL AND url <> ''",
    ]
    params: list[Any] = []
    if source_id is not None:
        clauses.append("source_id = %s")
        params.append(source_id)
    if run_id is not None:
        clauses.append("run_id = %s")
        params.append(run_id)

    sql = f"SELECT COUNT(*) AS n FROM scraped_pages WHERE {' AND '.join(clauses)}"
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row["n"]) if row else 0
    except Exception:
        return 0


# ── Transformação ─────────────────────────────────────────────────────────────

def build_article_from_scraped_page(
    page: dict,
    source: dict | None = None,
) -> dict | None:
    """
    Transforma um registro de scraped_pages em item compatível com upsert_article().

    Retorna None se os campos obrigatórios (title, url) estiverem ausentes.
    Não escreve nada no banco.
    """
    title = strip_html(page.get("title") or "").strip()
    url = (page.get("url") or "").strip()

    if not title:
        raise ValueError("title obrigatório está ausente ou vazio")
    if not url:
        raise ValueError("url obrigatório está ausente ou vazio")

    canonical = canonicalize_url(url)
    art_id = article_id(canonical, title)

    # Resumo: prefere content_text, cai em string vazia
    raw_content = page.get("content_text") or ""
    summary = strip_html(raw_content[:500]).strip()

    # Data: prefere published_at da page, cai em fetched_at
    published_at = page.get("published_at") or page.get("fetched_at") or None

    # Scope e trust: prefere dados da source vinculada, fallback seguro
    scope = (
        (source or {}).get("scope")
        or page.get("source_scope")
        or "brasil"
    )
    trust = float(
        (source or {}).get("trust")
        or page.get("source_trust")
        or 0.5
    )
    source_name = (
        (source or {}).get("name")
        or page.get("source_name")
        or "scraping"
    )

    raw_json = json_dumps({
        "origin": "scraping",
        "scraped_page_id": page.get("id"),
        "source_id": page.get("source_id"),
        "run_id": page.get("run_id"),
        "fetched_at": str(page.get("fetched_at") or ""),
        "extraction_status": page.get("extraction_status"),
    })

    item: dict[str, Any] = {
        "id": art_id,
        "title": title,
        "url": url,
        "canonical_url": canonical,
        "source": source_name,
        "source_scope": scope,
        "source_trust": trust,
        "published_at": published_at,
        "summary": summary,
        "content": raw_content[:5000] if raw_content else summary,
        "title_signature": title_signature(title),
        "raw_json": raw_json,
    }

    scores = automatic_scores(item)
    item.update(scores)
    return item


# ── Marcação de status ─────────────────────────────────────────────────────────

def mark_scraped_page_ingested(page_id: int, article_id_val: str) -> None:
    """Marca scraped_page como ingested, registrando o article_id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scraped_pages
                SET ingestion_status = 'ingested',
                    article_id       = %s,
                    ingested_at      = NOW(),
                    ingestion_error  = NULL
                WHERE id = %s
                """,
                (article_id_val, page_id),
            )


def mark_scraped_page_ingestion_error(page_id: int, error_message: str) -> None:
    """Marca scraped_page como erro de ingestão."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scraped_pages
                SET ingestion_status = 'error',
                    ingestion_error  = %s
                WHERE id = %s
                """,
                (error_message[:500], page_id),
            )


# ── Função principal ──────────────────────────────────────────────────────────

def ingest_scraped_pages(
    source_id: int | None = None,
    run_id: int | None = None,
    limit: int = 50,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Ingere páginas extraídas com sucesso (scraped_pages) no pipeline articles.

    Reutiliza upsert_article() e automatic_scores() — mesma lógica do RSS.
    Cada página é processada isoladamente: erro em uma não interrompe as demais.

    dry_run=True: roda toda a lógica, mas não persiste artigos nem atualiza
                  ingestion_status em scraped_pages.

    Retorna dict com contagens e lista de erros.
    """
    now = utc_now()
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "eligible": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_duplicate": 0,
        "errors": 0,
        "error_details": [],
        "started_at": now.isoformat(),
    }

    pages = get_eligible_pages(source_id=source_id, run_id=run_id, limit=limit)
    result["eligible"] = len(pages)

    if not pages:
        result["message"] = "Nenhuma página elegível para ingestão."
        return result

    # Cada página é processada em sua própria transação para garantir que
    # upsert_article e a atualização de scraped_pages commitem juntos.
    # Isso evita a violação de FK: a FK article_id só existe após o commit do artigo.
    for page in pages:
        page_id = page["id"]
        page_url = page.get("url", "?")

        try:
            item = build_article_from_scraped_page(page)

            if dry_run:
                # Verifica duplicata sem persistir nada
                with connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id FROM articles WHERE canonical_url = %s LIMIT 1",
                            (item["canonical_url"],),
                        )
                        existing = cur.fetchone()
                if existing:
                    result["skipped_duplicate"] += 1
                else:
                    result["inserted"] += 1
                continue

            # Ingestão real: artigo + marking no mesmo commit
            with connect() as conn:
                inserted = upsert_article(conn, item)

                # Busca o ID real do artigo no banco (pode diferir de item["id"]
                # quando upsert fez UPDATE via title_signature de artigo pré-existente)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM articles WHERE canonical_url = %s LIMIT 1",
                        (item["canonical_url"],),
                    )
                    row = cur.fetchone()
                actual_article_id = row["id"] if row else item["id"]

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE scraped_pages
                        SET ingestion_status = 'ingested',
                            article_id       = %s,
                            ingested_at      = NOW(),
                            ingestion_error  = NULL
                        WHERE id = %s
                        """,
                        (actual_article_id, page_id),
                    )
            if inserted:
                result["inserted"] += 1
            else:
                result["updated"] += 1

        except Exception as exc:
            result["errors"] += 1
            result["error_details"].append({
                "page_id": page_id,
                "url": page_url,
                "error": str(exc)[:200],
            })
            _logger.warning(
                "Erro ao ingerir scraped_page id=%s url=%s: %s",
                page_id, page_url, str(exc)[:120],
            )
            try:
                mark_scraped_page_ingestion_error(page_id, str(exc)[:500])
            except Exception:
                pass

    result["finished_at"] = utc_now().isoformat()
    return result
