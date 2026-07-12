from __future__ import annotations

from flask import Blueprint, jsonify

from o_rugido.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from o_rugido.services.monitoring import (
    alerts,
    api_health,
    containers_health,
    db_health,
    dispatch_critical_alerts,
    host_health,
    internal_services_health,
    n8n_health,
    pipeline_health,
    serper_health,
    telegram_health,
)

bp = Blueprint("monitor", __name__)


@bp.get("/monitor/api")
def monitor_api():
    return jsonify(api_health())


@bp.get("/monitor/host")
def monitor_host():
    return jsonify(host_health())


@bp.get("/monitor/db")
def monitor_db():
    return jsonify(db_health())


@bp.get("/monitor/pipeline")
def monitor_pipeline():
    return jsonify(pipeline_health())


@bp.get("/monitor/n8n")
def monitor_n8n():
    return jsonify(n8n_health())


@bp.get("/monitor/services")
def monitor_services():
    return jsonify(internal_services_health())


@bp.get("/monitor/telegram")
def monitor_telegram():
    return jsonify(telegram_health(TELEGRAM_BOT_TOKEN))


@bp.get("/monitor/containers")
def monitor_containers():
    return jsonify(containers_health())


@bp.get("/monitor/serper")
def monitor_serper():
    return jsonify(serper_health())


@bp.get("/monitor/all")
def monitor_all():
    """Snapshot completo. Usado pelo dashboard."""
    api = api_health()
    host = host_health()
    db = db_health()
    pipeline = pipeline_health()
    services = internal_services_health()
    telegram = telegram_health(TELEGRAM_BOT_TOKEN)
    n8n = n8n_health()
    containers = containers_health()
    serper = serper_health()

    active_alerts = alerts(pipeline, n8n)

    return jsonify({
        "api": api,
        "host": host,
        "db": db,
        "pipeline": pipeline,
        "services": services,
        "telegram": telegram,
        "n8n": n8n,
        "containers": containers,
        "serper": serper,
        "alerts": active_alerts,
    })


@bp.post("/monitor/dispatch-alerts")
def monitor_dispatch_alerts():
    """Chamado por cron (n8n) periodicamente. Envia alertas criticos
    ao chat do editor via Telegram, com dedupe de 1h por mensagem."""
    pipeline = pipeline_health()
    n8n = n8n_health()
    active_alerts = alerts(pipeline, n8n)
    result = dispatch_critical_alerts(
        active_alerts,
        TELEGRAM_CHAT_ID,
        TELEGRAM_BOT_TOKEN,
    )
    return jsonify(result)
