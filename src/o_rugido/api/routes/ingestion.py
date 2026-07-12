"""Rotas de ingestão: coleta RSS, ranking, cleanup, stats."""
from __future__ import annotations

from flask import Blueprint, request

from ..app import cli_json

bp = Blueprint("ingestion", __name__)


@bp.post("/pipeline/collect")
def pipeline_collect():
    limit = (request.json or {}).get("limit_per_feed", 30)
    return cli_json("collect", "--limit-per-feed", str(limit), timeout=180)


@bp.post("/pipeline/rank")
def pipeline_rank():
    return cli_json("rank", timeout=90)


@bp.post("/pipeline/cleanup")
def pipeline_cleanup():
    d = request.json or {}
    return cli_json("cleanup", "--days", str(d.get("days", 30)))


@bp.get("/stats")
def get_stats():
    return cli_json("stats")
