"""
Registro de ações editoriais para auditoria.
Fase 2 — tabela editorial_actions: quem fez o quê, quando e em qual artigo/dispatch.
"""
from __future__ import annotations

from news_radar.core.db import connect, json_dumps


def record_editorial_action(
    action: str,
    actor: str = "system",
    article_id: str | None = None,
    dispatch_id: int | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Insere ação editorial e retorna o id gerado.

    Campos obrigatórios: action, actor.
    article_id e dispatch_id são opcionais para eventos de sistema sem alvo específico.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
                INSERT INTO editorial_actions
                    (article_id, dispatch_id, action, actor,
                     from_status, to_status, notes, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
            (
                article_id,
                dispatch_id,
                action,
                actor,
                from_status,
                to_status,
                notes,
                json_dumps(metadata),
            ),
        )
        return cur.fetchone()["id"]


def list_editorial_actions_for_target(
    article_id: str | None = None,
    dispatch_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Lista ações editoriais por artigo e/ou dispatch, mais recentes primeiro.

    Sem filtros retorna as `limit` ações mais recentes do sistema.
    """
    conditions: list[str] = []
    params: list = []
    if article_id is not None:
        conditions.append("article_id = %s")
        params.append(article_id)
    if dispatch_id is not None:
        conditions.append("dispatch_id = %s")
        params.append(dispatch_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
                SELECT * FROM editorial_actions
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
            params,
        )
        return [dict(row) for row in cur.fetchall()]
