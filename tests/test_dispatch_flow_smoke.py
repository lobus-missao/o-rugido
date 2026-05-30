from __future__ import annotations

from contextlib import contextmanager

from news_radar import dispatch


class FakeCursor:
    def __init__(self):
        self.calls = 0
        self.updated = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls += 1
        if query.strip().startswith("UPDATE articles"):
            self.updated.append((query, params))

    def fetchall(self):
        if self.calls == 1:
            return [{"article_id": "old"}]
        return [
            {"id": "art-1", "title": "A", "final_score_brasil": 90},
            {"id": "old", "title": "Old", "final_score_brasil": 89},
            {"id": "art-2", "title": "B", "final_score_brasil": 80},
            {"id": "art-3", "title": "C", "final_score_brasil": 70},
        ]


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


@contextmanager
def fake_connect():
    yield FakeConn()


def test_select_top_articles_excludes_already_dispatched(monkeypatch):
    monkeypatch.setattr(dispatch, "connect", fake_connect)

    selected = dispatch.select_top_articles("morning", scope="brasil", top=3)

    assert [item["id"] for item in selected] == ["art-1", "art-2", "art-3"]


def test_approve_news_records_reviewer_without_generating_card(monkeypatch):
    updates = []
    monkeypatch.setattr(dispatch, "get_dispatch", lambda dispatch_id: {
        "id": dispatch_id,
        "article_id": "art-1",
        "status": "pending_article",
        "article_tg_message_id": None,
    })
    monkeypatch.setattr(dispatch, "update_dispatch", lambda dispatch_id, **fields: updates.append(fields))
    monkeypatch.setattr(dispatch, "_try_claim_dispatch", lambda *a: True)

    result = dispatch.approve_article(10, "Editor Teste", generate_card=False, dry_run=True)

    assert result["status"] == "article_approved"
    assert updates[0]["status"] == "article_approved"
    assert updates[0]["article_reviewed_by"] == "Editor Teste"
    assert updates[0]["article_reviewed_at"] is not None


def test_generate_card_for_dispatch_sets_pending_card(monkeypatch, tmp_path):
    card_path = tmp_path / "card.png"
    card_path.write_bytes(b"png")
    updates = []
    monkeypatch.setattr(dispatch, "get_dispatch", lambda dispatch_id: {
        "id": dispatch_id,
        "article_id": "art-1",
        "scope": "brasil",
        "status": "article_approved",
    })
    monkeypatch.setattr(dispatch, "update_dispatch", lambda dispatch_id, **fields: updates.append(fields))

    import news_radar.card_renderer as card_renderer
    monkeypatch.setattr(card_renderer, "render_cards", lambda **kwargs: [{"card_path": str(card_path)}])

    result = dispatch.generate_card_for_dispatch(10, "Editor Teste", dry_run=True)

    assert result["status"] == "pending_card"
    assert any(update.get("status") == "pending_card" for update in updates)
    assert any(update.get("card_tg_message_id") == "0" for update in updates)


def test_approve_card_marks_ready_to_publish(monkeypatch):
    updates = []
    fake_conn = FakeConn()

    @contextmanager
    def fake_article_connect():
        yield fake_conn

    monkeypatch.setattr(dispatch, "get_dispatch", lambda dispatch_id: {
        "id": dispatch_id,
        "article_id": "art-1",
        "status": "pending_card",
        "card_tg_message_id": None,
    })
    monkeypatch.setattr(dispatch, "update_dispatch", lambda dispatch_id, **fields: updates.append(fields))
    monkeypatch.setattr(dispatch, "connect", fake_article_connect)

    result = dispatch.approve_card(10, "Editor Teste")

    assert result["status"] == "ready_to_publish"
    assert updates[0]["status"] == "ready_to_publish"
    assert updates[0]["card_reviewed_by"] == "Editor Teste"
    assert updates[0]["ready_at"] is not None
