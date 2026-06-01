from __future__ import annotations

import api_server
from news_radar.api import app as http_app


def test_health_endpoint():
    client = api_server.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_stats_endpoint_returns_cli_status(monkeypatch):
    monkeypatch.setattr(
        http_app,
        "run_cli",
        lambda *args, **kwargs: ({"ok": True, "total_articles": 0}, 200),
    )
    client = api_server.app.test_client()
    response = client.get("/stats")
    assert response.status_code == 200
    assert response.get_json()["total_articles"] == 0


def test_api_preserves_cli_error_status(monkeypatch):
    monkeypatch.setattr(
        http_app,
        "run_cli",
        lambda *args, **kwargs: ({"ok": False, "error": "falhou"}, 500),
    )
    client = api_server.app.test_client()
    response = client.post("/pipeline/rank")
    assert response.status_code == 500
    assert response.get_json()["ok"] is False


def test_pipeline_collect_runs_cli(monkeypatch):
    captured = {}

    def fake(*args, **kwargs):
        captured["args"] = args
        return ({"ok": True, "feeds_total": 2, "inserted": 5, "updated": 1}, 200)

    monkeypatch.setattr(http_app, "run_cli", fake)
    client = api_server.app.test_client()
    response = client.post("/pipeline/collect", json={"limit_per_feed": 10})

    assert response.status_code == 200
    assert response.get_json()["inserted"] == 5
    assert "collect" in captured["args"]
