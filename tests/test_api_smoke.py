from __future__ import annotations

import api_server


def test_health_endpoint():
    client = api_server.app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_stats_endpoint_returns_cli_status(monkeypatch):
    monkeypatch.setattr(api_server, "cli", lambda *args, **kwargs: ({"ok": True, "total_articles": 0}, 200))
    client = api_server.app.test_client()

    response = client.get("/stats")

    assert response.status_code == 200
    assert response.get_json()["total_articles"] == 0


def test_api_preserves_cli_error_status(monkeypatch):
    monkeypatch.setattr(api_server, "cli", lambda *args, **kwargs: ({"ok": False, "error": "falhou"}, 500))
    client = api_server.app.test_client()

    response = client.post("/pipeline/rank")

    assert response.status_code == 500
    assert response.get_json()["ok"] is False


def test_editorial_top3_endpoint(monkeypatch):
    import news_radar.dispatch as dispatch

    monkeypatch.setattr(dispatch, "select_top_articles", lambda **kwargs: [{"id": "art-1", "final_score_brasil": 90}])
    client = api_server.app.test_client()

    response = client.get("/api/editorial/top3?edition=morning&scope=brasil&top=3")

    assert response.status_code == 200
    assert response.get_json()["count"] == 1


def test_review_card_endpoint_marks_ready(monkeypatch):
    import news_radar.dispatch as dispatch

    monkeypatch.setattr(
        dispatch,
        "approve_card",
        lambda dispatch_id, reviewer: {"ok": True, "dispatch_id": dispatch_id, "status": "ready_to_publish"},
    )
    client = api_server.app.test_client()

    response = client.post("/api/review/card", json={
        "dispatch_id": 10,
        "action": "approve",
        "reviewer": "Editor",
    })

    assert response.status_code == 200
    assert response.get_json()["status"] == "ready_to_publish"
