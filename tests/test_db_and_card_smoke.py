from __future__ import annotations

import os

import pytest

from news_radar.services.rendering import _render_html


def test_render_card_html_smoke():
    html = _render_html(
        {
            "id": "art-1",
            "title": "Título de teste",
            "summary": "Resumo de teste para card editorial.",
            "source": "Fonte",
            "published_at": "2026-05-28T10:00:00+00:00",
            "priority": "alta",
            "category": "Poder",
            "final_score_brasil": 72,
            "ai_json": {"pontos_chave": ["Ponto 1"], "entidades": ["TCE-PI"]},
        },
        """
        <div id="card">
          {{titulo}} {{editoria}} {{prioridade}} {{resumo}}
          <ul>{{pontos_chave}}</ul>
          {{fonte}} {{score}} {{entidades_tags}}
        </div>
        """,
    )

    assert "Título de teste" in html
    assert "Poder" in html
    assert "ALTA" in html
    assert "TCE-PI" in html


def test_init_db_smoke_against_configured_postgres(monkeypatch):
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("Defina TEST_DATABASE_URL para rodar o smoke real de PostgreSQL.")

    import news_radar.core.db as db

    monkeypatch.setattr(db, "DATABASE_URL", test_database_url)
    db.init_db()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('articles', 'ai_batches', 'dispatches')
            """)
            tables = {row["table_name"] for row in cur.fetchall()}

    assert {"articles", "ai_batches", "dispatches"} <= tables
