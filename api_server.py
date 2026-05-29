"""
API HTTP local — bridge entre n8n e o CLI do news-radar.
Necessário em produção Docker (containers separados).
Em dev local pode usar o Code node do n8n com child_process.
Porta: 8888
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

ROOT = Path(__file__).parent
PYTHON = sys.executable
CLI = [PYTHON, "-m", "news_radar.cli"]

app = Flask(__name__)


def cli(*args, timeout=300) -> tuple[dict, int]:
    """Executa CLI e retorna (dict, http_status). Não tem lógica de negócio."""
    r = subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=timeout,
    )
    if r.returncode == 0:
        try:
            parsed = json.loads(r.stdout)
            if isinstance(parsed, dict):
                return {"ok": True, **parsed}, 200
            return {"ok": True, "data": parsed}, 200
        except Exception:
            return {"ok": True, "output": r.stdout.strip()[:500]}, 200
    return {"ok": False, "error": r.stderr.strip()[-500:]}, 500


def cli_json(*args, timeout=300):
    payload, status = cli(*args, timeout=timeout)
    return jsonify(payload), status


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def api_json(payload: dict, status: int = 200):
    return jsonify(json_ready(payload)), status


def _bool_arg(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


@contextmanager
def dry_run_env(enabled: bool):
    previous = os.getenv("NEWS_RADAR_DRY_RUN")
    if enabled:
        os.environ["NEWS_RADAR_DRY_RUN"] = "1"
    try:
        yield
    finally:
        if enabled:
            if previous is None:
                os.environ.pop("NEWS_RADAR_DRY_RUN", None)
            else:
                os.environ["NEWS_RADAR_DRY_RUN"] = previous


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/pipeline/collect")
def pipeline_collect():
    limit = (request.json or {}).get("limit_per_feed", 30)
    return cli_json("collect", "--limit-per-feed", str(limit), timeout=180)


@app.post("/pipeline/rank")
def pipeline_rank():
    return cli_json("rank", timeout=90)


@app.post("/pipeline/make-batches")
def pipeline_make_batches():
    d = request.json or {}
    return cli_json(
        "make-ai-batches",
        "--scope", d.get("scope", "brasil"),
        "--top", str(d.get("top", 200)),
        "--batch-size", str(d.get("batch_size", 30)),
        "--days-back", str(d.get("days_back", 3)),
    )


@app.post("/pipeline/cleanup")
def pipeline_cleanup():
    d = request.json or {}
    return cli_json(
        "cleanup",
        "--days", str(d.get("days", 30)),
        "--expire-batches-hours", str(d.get("expire_batches_hours", 48)),
    )


@app.get("/stats")
def get_stats():
    return cli_json("stats")


@app.get("/batches")
def get_batches():
    s = request.args.get("status")
    args = ["list-ai-batches", "--status", s] if s else ["list-ai-batches"]
    return cli_json(*args)


@app.post("/cards/update-status")
def update_card():
    d = request.json or {}
    article_id = d.get("article_id")
    status = d.get("status")
    if not article_id or not status:
        return jsonify({"ok": False, "error": "article_id e status obrigatorios"}), 400
    return cli_json("update-card-status", "--article-id", article_id, "--status", status)


@app.get("/api/editorial/top3")
def api_editorial_top3():
    from news_radar.dispatch import select_top_articles

    edition = request.args.get("edition", "morning")
    scope = request.args.get("scope", "brasil")
    top = int(request.args.get("top", 3))
    articles = select_top_articles(edition=edition, scope=scope, top=top)
    return api_json({"ok": True, "edition": edition, "scope": scope, "count": len(articles), "articles": articles})


@app.post("/api/dispatch/run")
def api_dispatch_run():
    from news_radar.dispatch import create_dispatch

    d = request.json or {}
    edition = d.get("edition", "morning")
    scope = d.get("scope", "brasil")
    top = int(d.get("top", 3))
    dry_run = _bool_arg(d.get("dry_run"))
    created = create_dispatch(edition=edition, scope=scope, top=top, dry_run=dry_run)
    return api_json({
        "ok": True,
        "edition": edition,
        "scope": scope,
        "dry_run": dry_run,
        "count": len(created),
        "dispatches": created,
    })


@app.post("/api/review/news")
def api_review_news():
    from news_radar.dispatch import approve_article, reject_article

    d = request.json or {}
    dispatch_id = d.get("dispatch_id")
    action = d.get("action")
    reviewer = d.get("reviewer") or d.get("user") or "n8n"
    dry_run = _bool_arg(d.get("dry_run"))
    generate_card = _bool_arg(d.get("generate_card"), default=False)
    if not dispatch_id or action not in {"approve", "reject"}:
        return jsonify({"ok": False, "error": "dispatch_id e action=approve|reject obrigatorios"}), 400

    with dry_run_env(dry_run):
        if action == "approve":
            result = approve_article(int(dispatch_id), reviewer, generate_card=generate_card, dry_run=dry_run)
        else:
            result = reject_article(int(dispatch_id), reviewer)
    return api_json({**result, "dry_run": dry_run})


@app.post("/api/cards/generate")
def api_cards_generate():
    from news_radar.dispatch import generate_card_for_dispatch

    d = request.json or {}
    dispatch_id = d.get("dispatch_id")
    reviewer = d.get("reviewer") or d.get("user") or "n8n"
    dry_run = _bool_arg(d.get("dry_run"))
    if not dispatch_id:
        return jsonify({"ok": False, "error": "dispatch_id obrigatorio"}), 400

    with dry_run_env(dry_run):
        result = generate_card_for_dispatch(int(dispatch_id), user=reviewer, dry_run=dry_run)
    return api_json({**result, "dry_run": dry_run})


@app.post("/api/review/card")
def api_review_card():
    from news_radar.dispatch import approve_card, reject_card

    d = request.json or {}
    dispatch_id = d.get("dispatch_id")
    action = d.get("action")
    reviewer = d.get("reviewer") or d.get("user") or "n8n"
    dry_run = _bool_arg(d.get("dry_run"))
    if not dispatch_id or action not in {"approve", "reject"}:
        return jsonify({"ok": False, "error": "dispatch_id e action=approve|reject obrigatorios"}), 400

    with dry_run_env(dry_run):
        result = approve_card(int(dispatch_id), reviewer) if action == "approve" else reject_card(int(dispatch_id), reviewer)
    return api_json({**result, "dry_run": dry_run})


@app.get("/api/dispatch/status")
def api_dispatch_status():
    from news_radar.dispatch import EDITIONS, get_edition_dispatches

    edition = request.args.get("edition")
    raw_date = request.args.get("date")
    edition_date = date.fromisoformat(raw_date) if raw_date else date.today()
    editions = [edition] if edition else list(EDITIONS)
    result = {
        item: get_edition_dispatches(item, edition_date)
        for item in editions
    }
    return api_json({"ok": True, "date": edition_date.isoformat(), "editions": result})


@app.post("/api/telegram/callback")
def api_telegram_callback():
    from news_radar.dispatch import handle_callback_action

    body = request.json or {}
    callback = body.get("callback_query") or body
    data = callback.get("data", "")
    if ":" not in data:
        return jsonify({"ok": False, "error": "callback data invalido"}), 400

    action, payload = data.split(":", 1)
    user_data = callback.get("from") or {}
    reviewer = user_data.get("username") or user_data.get("first_name") or "Telegram"
    result = handle_callback_action(action, payload, reviewer)
    return api_json(result, 200 if result.get("ok") else 400)


@app.get("/api/scheduler/status")
def api_scheduler_status():
    """Retorna estado do scheduler interno (válido apenas neste processo)."""
    from news_radar.scheduler import get_status
    return api_json({"ok": True, **get_status()})


# ---------------------------------------------------------------------------
# Inicialização do scheduler interno (opcional)
# Ativação: NEWS_RADAR_SCHEDULER=1 no .env
# Aviso: BackgroundScheduler é single-process. Ver scheduler.py para detalhes.
# ---------------------------------------------------------------------------
from news_radar.scheduler import start_scheduler as _start_scheduler
_start_scheduler()


if __name__ == "__main__":
    print("News Radar API — http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, debug=False)
