from __future__ import annotations

import api_server
from o_rugido.api.routes import ingestion as ingestion_route


def test_health_endpoint():
    client = api_server.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_stats_endpoint_returns_service_output(monkeypatch):
    monkeypatch.setattr(ingestion_route, "stats", lambda: {"total_articles": 0})
    client = api_server.app.test_client()
    response = client.get("/stats")
    assert response.status_code == 200
    assert response.get_json()["total_articles"] == 0


def test_api_returns_500_on_service_error(monkeypatch):
    def boom():
        raise RuntimeError("falhou")
    monkeypatch.setattr(ingestion_route, "rank_all", boom)
    client = api_server.app.test_client()
    response = client.post("/pipeline/rank")
    assert response.status_code == 500
    assert response.get_json()["ok"] is False
    assert "falhou" in response.get_json()["error"]


def test_pipeline_collect_calls_service(monkeypatch):
    captured = {}

    def fake(limit_per_feed):
        captured["limit"] = limit_per_feed
        return {"feeds_total": 2, "inserted": 5, "updated": 1}

    monkeypatch.setattr(ingestion_route, "collect_feeds", fake)
    client = api_server.app.test_client()
    response = client.post("/pipeline/collect", json={"limit_per_feed": 10})

    assert response.status_code == 200
    assert response.get_json()["inserted"] == 5
    assert captured["limit"] == 10
