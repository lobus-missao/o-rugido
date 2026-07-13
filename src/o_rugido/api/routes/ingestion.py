"""Rotas de ingestão: coleta RSS, ranking, cleanup, stats."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from o_rugido.core.db import connect
from o_rugido.repositories.articles import stats
from o_rugido.services.ingestion import collect_feeds
from o_rugido.services.ranker import rank_all

bp = Blueprint("ingestion", __name__)
_logger = logging.getLogger(__name__)


def _default_serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


@bp.post("/pipeline/collect")
def pipeline_collect():
    limit = (request.json or {}).get("limit_per_feed", 30)
    try:
        result = collect_feeds(limit_per_feed=int(limit))
    except Exception as exc:
        _logger.exception("collect_feeds falhou")
        return jsonify({"ok": False, "error": str(exc)[:400]}), 500
    return jsonify({"ok": True, **result})


@bp.post("/pipeline/rank")
def pipeline_rank():
    try:
        count = rank_all()
    except Exception as exc:
        _logger.exception("rank_all falhou")
        return jsonify({"ok": False, "error": str(exc)[:400]}), 500
    return jsonify({"ok": True, "ranked": count})


@bp.post("/pipeline/cleanup")
def pipeline_cleanup():
    days = int((request.json or {}).get("days", 30))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM articles "
                "WHERE published_at < %s AND card_status NOT IN ('approved')",
                (cutoff,),
            )
            deleted = cur.rowcount
    except Exception as exc:
        _logger.exception("cleanup falhou")
        return jsonify({"ok": False, "error": str(exc)[:400]}), 500
    return jsonify({"ok": True, "deleted_articles": deleted, "days": days})


@bp.get("/stats")
def get_stats():
    try:
        data = stats()
    except Exception as exc:
        _logger.exception("stats falhou")
        return jsonify({"ok": False, "error": str(exc)[:400]}), 500
    return jsonify({"ok": True, **data})
