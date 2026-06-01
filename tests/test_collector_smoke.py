from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from news_radar.services import ingestion as collector


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None


class FakeConn:
    def cursor(self):
        return FakeCursor()

    def rollback(self):
        return None


@contextmanager
def fake_connect():
    yield FakeConn()


def test_collect_feeds_with_mocked_rss(monkeypatch):
    entry = SimpleNamespace(
        title="Prefeitura abre licitacao para obra",
        link="https://example.com/noticia?utm_source=x",
        summary="Contrato publico para obra em Teresina.",
        published="Thu, 28 May 2026 10:00:00 GMT",
    )
    parsed = SimpleNamespace(entries=[entry], bozo=False)

    monkeypatch.setattr(collector, "init_db", lambda: None)
    monkeypatch.setattr(collector, "connect", fake_connect)
    monkeypatch.setattr(
        collector,
        "load_feeds_config",
        lambda: {"feeds": [{"name": "Fonte", "url": "https://example.com/rss", "scope": "teresina", "trust": 0.8}]},
    )
    monkeypatch.setattr(collector.feedparser, "parse", lambda url: parsed)
    monkeypatch.setattr(collector, "upsert_article", lambda conn, item: True)

    result = collector.collect_feeds(limit_per_feed=10)

    assert result["feeds_total"] == 1
    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["errors"] == []
