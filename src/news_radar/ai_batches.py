from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AI_BATCHES_DIR, AI_RESULTS_DIR, PROMPTS_DIR, ensure_dirs
from .db import connect, json_dumps, utc_now
from .ranker import ai_score_from_payload, combine_with_ai
from .repository import SCORE_COLUMN, top_articles
from .text_utils import normalize_spaces

DEFAULT_MIN_BATCH_TOKENS = 32_000
DEFAULT_TARGET_BATCH_TOKENS = 96_000
DEFAULT_MAX_BATCH_TOKENS = 128_000
DEFAULT_MAX_BATCH_CHARS = 400_000
DEFAULT_MAX_BATCH_WORDS = 96_000
DEFAULT_BATCH_ITEMS = 100


def compact_article(article: dict[str, Any]) -> dict[str, Any]:
    summary = normalize_spaces(article.get("summary") or "")
    if len(summary) > 900:
        summary = summary[:900].rsplit(" ", 1)[0] + "..."
    return {
        "id": article["id"],
        "titulo": article.get("title"),
        "fonte": article.get("source"),
        "data_publicacao": str(article.get("published_at") or "")[:16],
        "resumo": summary,
        "url": article.get("canonical_url") or article.get("url"),
    }


SCOPE_CONTEXT = {
    "brasil": """ESCOPO: BRASIL (visao nacional)
Foco em noticias de alcance nacional com impacto em politica, economia, justica e servicos publicos federais.
Principais orgaos de referencia: STF, STJ, TCU, CGU, PF, MPF, Senado, Camara dos Deputados, ministerios federais.
Relevancia_local alta quando afeta diretamente o Piaui ou o Nordeste.""",

    "piaui": """ESCOPO: PIAUI (visao estadual)
Foco em noticias do estado do Piaui. Relevancia_local alta quando envolve Teresina, Parnaiba, Picos ou municipios piauienses.
Principais orgaos: ALEPI (Assembleia Legislativa), TCE-PI, MPPI, TJPI, Governo do Estado, Secretarias estaduais.
Governador atual: Rafael Fonteles. Partido: PT.
Siglas importantes: SEDUC-PI (educacao), SESAPI (saude), SSP-PI (seguranca), SEMAR (meio ambiente).
Prioridade alta para contratos estaduais, operacoes do MPPI/TCE-PI, decisoes da ALEPI.""",

    "teresina": """ESCOPO: TERESINA (visao municipal)
Foco exclusivo em noticias da capital Teresina e sua area metropolitana.
Principais orgaos: Prefeitura de Teresina, Camara Municipal de Teresina, FMS (Fundacao Municipal de Saude), SEMEC (educacao municipal), STRANS (transporte), SEMDUH (habitacao), ETURB (urbanismo).
Siglas: HUT (Hospital de Urgencia de Teresina), UPA, ARSETE, SAAD.
Prioridade alta para: licitacoes municipais, obras na cidade, denuncias envolvendo vereadores ou servidores, interrupcao de servicos publicos municipais.""",
}


def build_prompt(scope: str, batch: list[dict[str, Any]]) -> str:
    template_path = PROMPTS_DIR / "ai_batch_prompt_template.txt"
    template = template_path.read_text(encoding="utf-8")
    payload = json.dumps(batch, ensure_ascii=False, indent=2)
    context = SCOPE_CONTEXT.get(scope, f"ESCOPO: {scope.upper()}")
    return (
        template.strip()
        + "\n\n"
        + context
        + "\n\n"
        + "LOTE DE NOTICIAS:\n"
        + payload
        + "\n"
    )


def estimate_text_metrics(text: str) -> dict[str, int]:
    words = len(text.split())
    chars = len(text)
    tokens = max(1, math.ceil(chars / 4))
    return {"estimated_tokens": tokens, "estimated_words": words, "estimated_chars": chars}


def estimate_batch_metrics(scope: str, batch: list[dict[str, Any]]) -> dict[str, int]:
    return estimate_text_metrics(build_prompt(scope, batch))


def _batch_row_to_dict(row) -> dict[str, Any]:
    return dict(row)


def _save_batch_record(
    batch_id: str,
    scope: str,
    article_count: int,
    prompt_path: Path,
    payload_path: Path,
) -> None:
    now = utc_now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_batches (
                    batch_id, scope, status, model, article_count, prompt_path, payload_path,
                    result_path, imported_count, ignored_count, error, created_at, started_at,
                    completed_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (batch_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    batch_id, scope, "pending", None, article_count,
                    str(prompt_path), str(payload_path),
                    None, 0, 0, None, now, None, None, now,
                ),
            )


def _partition_articles_by_items_with_budget(
    scope: str,
    articles: list[dict[str, Any]],
    *,
    batch_items: int,
    max_batch_tokens: int,
    max_batch_chars: int,
    max_batch_words: int,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []

    for article in articles:
        candidate_batch = current_batch + [article]
        candidate_metrics = estimate_batch_metrics(scope, candidate_batch)
        exceeds_max = (
            current_batch
            and (
                candidate_metrics["estimated_tokens"] > max_batch_tokens
                or candidate_metrics["estimated_words"] > max_batch_words
                or candidate_metrics["estimated_chars"] > max_batch_chars
            )
        )
        reached_item_limit = current_batch and len(current_batch) >= batch_items

        if exceeds_max or reached_item_limit:
            batches.append(current_batch)
            current_batch = [article]
        else:
            current_batch = candidate_batch

    if current_batch:
        batches.append(current_batch)

    return batches


def make_ai_batches(
    scope: str,
    top: int = 500,
    batch_size: int = DEFAULT_BATCH_ITEMS,
    min_batch_tokens: int = DEFAULT_MIN_BATCH_TOKENS,
    target_batch_tokens: int = DEFAULT_TARGET_BATCH_TOKENS,
    max_batch_tokens: int = DEFAULT_MAX_BATCH_TOKENS,
    max_batch_chars: int = DEFAULT_MAX_BATCH_CHARS,
    max_batch_words: int = DEFAULT_MAX_BATCH_WORDS,
    days_back: int | None = 3,
) -> list[dict[str, Any]]:
    if scope not in SCORE_COLUMN:
        raise ValueError("scope deve ser: brasil, piaui ou teresina")

    ensure_dirs()
    articles = top_articles(scope=scope, limit=top, days_back=days_back)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    generated: list[dict[str, Any]] = []
    compact_articles = [compact_article(article) for article in articles]

    partitions = _partition_articles_by_items_with_budget(
        scope,
        compact_articles,
        batch_items=batch_size,
        max_batch_tokens=max_batch_tokens,
        max_batch_chars=max_batch_chars,
        max_batch_words=max_batch_words,
    )

    for part, batch_articles in enumerate(partitions, start=1):
        if not batch_articles:
            continue

        batch_id = f"batch_{scope}_{timestamp}_part{part:02d}"
        payload_path = AI_BATCHES_DIR / f"{batch_id}.json"
        prompt_path = AI_BATCHES_DIR / f"{batch_id}.prompt.txt"
        prompt_text = build_prompt(scope, batch_articles)
        payload_text = json.dumps(batch_articles, ensure_ascii=False, indent=2)
        batch_metrics = estimate_text_metrics(prompt_text)

        payload_path.write_text(payload_text, encoding="utf-8")
        prompt_path.write_text(prompt_text, encoding="utf-8")
        _save_batch_record(
            batch_id=batch_id,
            scope=scope,
            article_count=len(batch_articles),
            prompt_path=prompt_path,
            payload_path=payload_path,
        )
        generated.append({
            "batch_id": batch_id,
            "json": str(payload_path),
            "prompt": str(prompt_path),
            "items": len(batch_articles),
            "status": "pending",
            **batch_metrics,
        })

    return generated


def list_ai_batches(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM ai_batches"
    params: list[Any] = []

    if status:
        query += " WHERE status = %s"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [_batch_row_to_dict(row) for row in cur.fetchall()]


def get_ai_batch(batch_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ai_batches WHERE batch_id = %s", (batch_id,))
            row = cur.fetchone()
    return _batch_row_to_dict(row) if row else None


def _update_batch_status(
    batch_id: str,
    *,
    status: str,
    model: str | None = None,
    result_path: str | None = None,
    imported_count: int | None = None,
    ignored_count: int | None = None,
    error: str | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    current = get_ai_batch(batch_id)
    if not current:
        raise ValueError(f"Lote nao encontrado: {batch_id}")

    started_at = current["started_at"]
    completed_at = current["completed_at"]
    if started and not started_at:
        started_at = utc_now()
    if completed:
        completed_at = utc_now()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ai_batches
                SET status = %s,
                    model = COALESCE(%s, model),
                    result_path = COALESCE(%s, result_path),
                    imported_count = COALESCE(%s, imported_count),
                    ignored_count = COALESCE(%s, ignored_count),
                    error = %s,
                    started_at = %s,
                    completed_at = %s,
                    updated_at = %s
                WHERE batch_id = %s
                """,
                (
                    status, model, result_path, imported_count, ignored_count,
                    error, started_at, completed_at, utc_now(), batch_id,
                ),
            )


def import_ai_result(path: str | Path, batch_id: str | None = None) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")

    content = path.read_text(encoding="utf-8").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    data = json.loads(content)
    if isinstance(data, dict):
        data = data.get("items") or data.get("result") or data.get("noticias") or []

    if not isinstance(data, list):
        raise ValueError("Resultado da IA precisa ser uma lista JSON.")

    updated = 0
    ignored = 0

    with connect() as conn:
        with conn.cursor() as cur:
            for item in data:
                if not isinstance(item, dict) or not item.get("id"):
                    ignored += 1
                    continue

                cur.execute(
                    """
                    SELECT id, auto_score_brasil, auto_score_piaui, auto_score_teresina
                    FROM articles WHERE id = %s
                    """,
                    (item["id"],),
                )
                row = cur.fetchone()

                if not row:
                    ignored += 1
                    continue

                ai_score = ai_score_from_payload(item)
                final_brasil = combine_with_ai(float(row["auto_score_brasil"]), ai_score)
                final_piaui = combine_with_ai(float(row["auto_score_piaui"]), ai_score)
                final_teresina = combine_with_ai(float(row["auto_score_teresina"]), ai_score)

                priority = item.get("prioridade") or item.get("priority")
                category = (
                    item.get("editoria") or item.get("ala")
                    or item.get("categoria") or item.get("category")
                )
                locality = item.get("localidade") or item.get("locality")
                entities = item.get("entidades") or item.get("entities") or []

                cur.execute(
                    """
                    UPDATE articles SET
                        ai_score = %s,
                        ai_json = %s,
                        category = %s,
                        locality = %s,
                        priority = %s,
                        entities_json = %s,
                        final_score_brasil = %s,
                        final_score_piaui = %s,
                        final_score_teresina = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        ai_score, json_dumps(item), category, locality, priority,
                        json_dumps(entities), final_brasil, final_piaui, final_teresina,
                        utc_now(), item["id"],
                    ),
                )
                updated += 1

    if batch_id:
        _update_batch_status(
            batch_id,
            status="completed",
            result_path=str(path),
            imported_count=updated,
            ignored_count=ignored,
            error=None,
            completed=True,
        )

    return {"updated": updated, "ignored": ignored, "file": str(path), "batch_id": batch_id}


def import_ai_result_detailed(
    path: str | Path,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Igual a import_ai_result mas retorna log detalhado por artigo."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")

    content = path.read_text(encoding="utf-8").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    data = json.loads(content)
    if isinstance(data, dict):
        data = data.get("items") or data.get("result") or data.get("noticias") or []

    if not isinstance(data, list):
        raise ValueError("Resultado da IA precisa ser uma lista JSON.")

    updated = 0
    ignored = 0
    logs: list[dict[str, Any]] = []

    with connect() as conn:
        with conn.cursor() as cur:
            for item in data:
                if not isinstance(item, dict) or not item.get("id"):
                    ignored += 1
                    logs.append({
                        "status": "ignorado",
                        "motivo": "item sem id ou formato inválido",
                        "id": item.get("id", "?") if isinstance(item, dict) else "?",
                        "titulo": None,
                        "fonte": None,
                        "editoria": None,
                        "prioridade": None,
                        "ai_score": None,
                    })
                    continue

                cur.execute(
                    """
                    SELECT id, title, source, source_scope,
                           auto_score_brasil, auto_score_piaui, auto_score_teresina
                    FROM articles WHERE id = %s
                    """,
                    (item["id"],),
                )
                row = cur.fetchone()

                if not row:
                    ignored += 1
                    logs.append({
                        "status": "não encontrado",
                        "motivo": "ID não existe no banco — pode ser de outro lote",
                        "id": item["id"],
                        "titulo": None,
                        "fonte": None,
                        "editoria": item.get("editoria") or item.get("categoria"),
                        "prioridade": item.get("prioridade") or item.get("priority"),
                        "ai_score": None,
                    })
                    continue

                try:
                    ai_score = ai_score_from_payload(item)
                    final_brasil = combine_with_ai(float(row["auto_score_brasil"]), ai_score)
                    final_piaui = combine_with_ai(float(row["auto_score_piaui"]), ai_score)
                    final_teresina = combine_with_ai(float(row["auto_score_teresina"]), ai_score)

                    priority = item.get("prioridade") or item.get("priority")
                    category = (
                        item.get("editoria") or item.get("ala")
                        or item.get("categoria") or item.get("category")
                    )
                    locality = item.get("localidade") or item.get("locality")
                    entities = item.get("entidades") or item.get("entities") or []

                    cur.execute(
                        """
                        UPDATE articles SET
                            ai_score = %s, ai_json = %s, category = %s, locality = %s,
                            priority = %s, entities_json = %s,
                            final_score_brasil = %s, final_score_piaui = %s,
                            final_score_teresina = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            ai_score, json_dumps(item), category, locality, priority,
                            json_dumps(entities), final_brasil, final_piaui, final_teresina,
                            utc_now(), item["id"],
                        ),
                    )
                    updated += 1
                    logs.append({
                        "status": "atualizado",
                        "motivo": None,
                        "id": row["id"],
                        "titulo": row["title"],
                        "fonte": row["source"],
                        "scope": row["source_scope"],
                        "editoria": category,
                        "prioridade": priority,
                        "ai_score": round(ai_score, 1),
                        "resumo": item.get("resumo_curto", ""),
                        "justificativa": item.get("justificativa_score", ""),
                    })

                except Exception as exc:
                    ignored += 1
                    logs.append({
                        "status": "erro",
                        "motivo": str(exc),
                        "id": item["id"],
                        "titulo": row["title"] if row else None,
                        "fonte": row["source"] if row else None,
                        "editoria": None,
                        "prioridade": None,
                        "ai_score": None,
                    })

    if batch_id:
        _update_batch_status(
            batch_id,
            status="completed",
            result_path=str(path),
            imported_count=updated,
            ignored_count=ignored,
            error=None,
            completed=True,
        )

    return {
        "updated": updated,
        "ignored": ignored,
        "file": str(path),
        "batch_id": batch_id,
        "logs": logs,
    }
