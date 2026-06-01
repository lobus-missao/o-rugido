"""
Testes da Fase 2 — Fontes (sources) e Ações Editoriais (editorial_actions).

Ref: docs/specs/02-data-model.md, docs/specs/03-ingestion-sources.md, docs/specs/11-audit-observability.md

Dois grupos:
  1. Testes de unidade com mocks — sem acesso ao banco, verificam lógica das queries.
  2. Smoke test de integração — requer TEST_DATABASE_URL, ignorado se ausente.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

import news_radar.repositories.sources as src_module
from news_radar.repositories import editorial_actions as ed_module


# ---------------------------------------------------------------------------
# Helpers de mock (mesmo padrão de test_dispatch_idempotency.py)
# ---------------------------------------------------------------------------

class _MockCursor:
    """Cursor configurável: captura execute() e retorna dados fixos."""

    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one
        self.executed: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params or ()))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _MockConn:
    def __init__(self, cursor: _MockCursor):
        self._cur = cursor

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _make_connect(cursor: _MockCursor):
    """Retorna context manager de conexão que usa o cursor mock."""
    @contextmanager
    def _connect():
        yield _MockConn(cursor)
    return _connect


# ===========================================================================
# Testes de list_sources
# ===========================================================================

def test_list_sources_sem_filtro_nao_tem_where(monkeypatch):
    """list_sources() sem argumentos não deve gerar cláusula WHERE."""
    cur = _MockCursor(rows=[{"id": 1, "name": "G1", "scope": "brasil"}])
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    result = src_module.list_sources()

    assert len(cur.executed) == 1
    query, _ = cur.executed[0]
    assert "WHERE" not in query
    assert len(result) == 1
    assert result[0]["name"] == "G1"


def test_list_sources_filtro_scope(monkeypatch):
    """list_sources(scope='piaui') deve incluir 'scope = %s' na query."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.list_sources(scope="piaui")

    query, params = cur.executed[0]
    assert "scope = %s" in query
    assert "piaui" in params


def test_list_sources_filtro_enabled_only(monkeypatch):
    """list_sources(enabled_only=True) deve incluir 'enabled = TRUE' na query."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.list_sources(enabled_only=True)

    query, params = cur.executed[0]
    assert "enabled = TRUE" in query


def test_list_sources_filtros_combinados(monkeypatch):
    """list_sources(scope='teresina', enabled_only=True) combina os dois filtros."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.list_sources(scope="teresina", enabled_only=True)

    query, params = cur.executed[0]
    assert "scope = %s" in query
    assert "enabled = TRUE" in query
    assert "teresina" in params


# ===========================================================================
# Testes de upsert_source
# ===========================================================================

def test_upsert_source_usa_on_conflict(monkeypatch):
    """upsert_source deve gerar INSERT ... ON CONFLICT ... DO UPDATE."""
    returned = {"id": 1, "name": "TestFeed", "url": "https://t.com/rss"}
    cur = _MockCursor(one=returned)
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    result = src_module.upsert_source("TestFeed", "https://t.com/rss")

    assert len(cur.executed) == 1
    query, _ = cur.executed[0]
    assert "ON CONFLICT" in query
    assert "DO UPDATE" in query
    assert result == returned


def test_upsert_source_passa_todos_os_campos(monkeypatch):
    """upsert_source envia name, url, source_type, scope, trust, enabled ao banco."""
    cur = _MockCursor(one={"id": 2, "name": "Feed", "url": "https://x.com"})
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.upsert_source(
        name="Feed",
        url="https://x.com",
        source_type="rss",
        scope="piaui",
        trust=0.75,
        enabled=False,
    )

    _, params = cur.executed[0]
    assert "Feed" in params
    assert "https://x.com" in params
    assert "rss" in params
    assert "piaui" in params
    assert 0.75 in params
    assert False in params


def test_upsert_source_defaults_razoaveis(monkeypatch):
    """upsert_source com apenas name e url usa source_type='rss', scope='piaui', trust=0.5."""
    cur = _MockCursor(one={"id": 3, "name": "Minimal", "url": "https://m.com"})
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.upsert_source("Minimal", "https://m.com")

    _, params = cur.executed[0]
    assert "rss" in params
    assert "piaui" in params
    assert 0.5 in params


# ===========================================================================
# Testes de mark_source_success
# ===========================================================================

def test_mark_source_success_usa_status_ok(monkeypatch):
    """mark_source_success deve definir last_status='ok' e error_count=0."""
    cur = _MockCursor()
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.mark_source_success(source_id=5)

    query, params = cur.executed[0]
    assert "'ok'" in query
    assert "error_count = 0" in query
    assert 5 in params


def test_mark_source_success_atualiza_last_run_at(monkeypatch):
    """mark_source_success deve definir last_run_at (não deixar NULL)."""
    cur = _MockCursor()
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.mark_source_success(source_id=1)

    query, _ = cur.executed[0]
    assert "last_run_at" in query


# ===========================================================================
# Testes de mark_source_error
# ===========================================================================

def test_mark_source_error_incrementa_error_count(monkeypatch):
    """mark_source_error deve incrementar error_count (não resetar)."""
    cur = _MockCursor()
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.mark_source_error(source_id=3, error_msg="Timeout ao conectar")

    query, params = cur.executed[0]
    assert "error_count + 1" in query
    assert "'error'" in query
    assert 3 in params


def test_mark_source_error_usa_status_error(monkeypatch):
    """mark_source_error deve definir last_status='error'."""
    cur = _MockCursor()
    monkeypatch.setattr(src_module, "connect", _make_connect(cur))

    src_module.mark_source_error(source_id=7, error_msg="404 Not Found")

    query, _ = cur.executed[0]
    assert "'error'" in query


# ===========================================================================
# Testes de record_editorial_action
# ===========================================================================

def test_record_editorial_action_retorna_id(monkeypatch):
    """record_editorial_action retorna o id inteiro da ação inserida."""
    cur = _MockCursor(one={"id": 42})
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    result = ed_module.record_editorial_action(
        action="approve_article",
        actor="editor@radar",
        article_id="abc123",
    )

    assert result == 42


def test_record_editorial_action_insere_em_editorial_actions(monkeypatch):
    """record_editorial_action deve gerar INSERT INTO editorial_actions."""
    cur = _MockCursor(one={"id": 1})
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.record_editorial_action(action="reject_article", actor="system")

    query, _ = cur.executed[0]
    assert "INSERT INTO editorial_actions" in query
    assert "RETURNING id" in query


def test_record_editorial_action_com_todos_os_campos(monkeypatch):
    """record_editorial_action aceita todos os campos opcionais."""
    cur = _MockCursor(one={"id": 10})
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.record_editorial_action(
        action="ai_import",
        actor="system",
        article_id="xyz789",
        dispatch_id=5,
        from_status="ai_done",
        to_status="selected",
        notes="Importado via lote batch_piaui_001",
        metadata={"batch_id": "batch_001", "match_pct": 0.82},
    )

    _, params = cur.executed[0]
    assert "xyz789" in params
    assert 5 in params
    assert "ai_import" in params
    assert "ai_done" in params
    assert "selected" in params


def test_record_editorial_action_sem_article_id(monkeypatch):
    """record_editorial_action funciona com article_id=None (evento de sistema)."""
    cur = _MockCursor(one={"id": 7})
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    result = ed_module.record_editorial_action(
        action="system_cleanup",
        actor="system",
    )

    assert result == 7
    _, params = cur.executed[0]
    # article_id é o primeiro parâmetro posicional → deve ser None
    assert params[0] is None


def test_record_editorial_action_sem_dispatch_id(monkeypatch):
    """record_editorial_action funciona com dispatch_id=None."""
    cur = _MockCursor(one={"id": 8})
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.record_editorial_action(
        action="card_generate",
        actor="system",
        article_id="art-001",
    )

    _, params = cur.executed[0]
    # dispatch_id é o segundo parâmetro → deve ser None
    assert params[1] is None


# ===========================================================================
# Testes de list_editorial_actions_for_target
# ===========================================================================

def test_list_actions_por_article_id(monkeypatch):
    """list_editorial_actions_for_target(article_id=X) filtra por artigo."""
    cur = _MockCursor(rows=[{"id": 1, "action": "approve_article", "article_id": "art-1"}])
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    result = ed_module.list_editorial_actions_for_target(article_id="art-1")

    query, params = cur.executed[0]
    assert "article_id = %s" in query
    assert "art-1" in params
    assert len(result) == 1


def test_list_actions_por_dispatch_id(monkeypatch):
    """list_editorial_actions_for_target(dispatch_id=X) filtra por dispatch."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.list_editorial_actions_for_target(dispatch_id=10)

    query, params = cur.executed[0]
    assert "dispatch_id = %s" in query
    assert 10 in params


def test_list_actions_sem_filtro_sem_where(monkeypatch):
    """list_editorial_actions_for_target() sem filtros não gera WHERE."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.list_editorial_actions_for_target()

    query, _ = cur.executed[0]
    assert "WHERE" not in query


def test_list_actions_limit_passado(monkeypatch):
    """list_editorial_actions_for_target respeita o parâmetro limit."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.list_editorial_actions_for_target(limit=10)

    _, params = cur.executed[0]
    assert 10 in params


def test_list_actions_article_e_dispatch_combinados(monkeypatch):
    """list_editorial_actions_for_target com article_id e dispatch_id combina os dois."""
    cur = _MockCursor(rows=[])
    monkeypatch.setattr(ed_module, "connect", _make_connect(cur))

    ed_module.list_editorial_actions_for_target(article_id="a1", dispatch_id=3)

    query, params = cur.executed[0]
    assert "article_id = %s" in query
    assert "dispatch_id = %s" in query
    assert "a1" in params
    assert 3 in params


# ===========================================================================
# Smoke test de integração contra banco real (TEST_DATABASE_URL)
# ===========================================================================

def test_sources_e_editorial_smoke_postgres(monkeypatch):
    """Smoke test completo: init_db, upsert, mark, record, list, cleanup.

    Requer: TEST_DATABASE_URL apontando para banco PostgreSQL de teste.
    """
    test_url = os.getenv("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Defina TEST_DATABASE_URL para rodar smoke de banco real.")

    import news_radar.core.db as db
    monkeypatch.setattr(db, "DATABASE_URL", test_url)

    # Repatchar connect nos módulos carregados para usar a URL de teste
    import importlib
    import news_radar.repositories.sources as src_real
    import news_radar.services.editorial as ed_real
    importlib.reload(src_real)
    importlib.reload(ed_real)
    monkeypatch.setattr(src_real, "connect", db.connect)
    monkeypatch.setattr(ed_real, "connect", db.connect)

    # Garante tabelas criadas (idempotente)
    db.init_db()

    # --- sources ---
    unique_name = f"__smoke_test_{os.getpid()}"
    s = src_real.upsert_source(
        name=unique_name,
        url="https://smoke.example.com/rss",
        source_type="rss",
        scope="brasil",
        trust=0.9,
    )
    assert s["id"] > 0, "upsert_source deve retornar id positivo"
    assert s["name"] == unique_name

    # Idempotência: mesmo name → mesmo id, URL atualizada
    s2 = src_real.upsert_source(
        name=unique_name,
        url="https://smoke.example.com/rss/v2",
        scope="brasil",
    )
    assert s2["id"] == s["id"], "upsert_source não deve criar duplicata por name"
    assert s2["url"] == "https://smoke.example.com/rss/v2", "url deve ser atualizada"

    src_real.mark_source_success(s["id"], collected_count=5)
    src_real.mark_source_error(s["id"], error_msg="Conexão recusada")

    listed = src_real.list_sources(scope="brasil")
    assert any(x["name"] == unique_name for x in listed), "source deve aparecer na listagem"

    # get_source_by_name
    found = src_real.get_source_by_name(unique_name)
    assert found is not None
    assert found["id"] == s["id"]

    # --- editorial_actions ---
    action_id = ed_real.record_editorial_action(
        action="smoke_test",
        actor="pytest",
        notes="Smoke test Fase 2",
        metadata={"pid": os.getpid()},
    )
    assert isinstance(action_id, int) and action_id > 0

    actions = ed_real.list_editorial_actions_for_target()
    assert any(a["id"] == action_id for a in actions)

    # Cleanup
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM editorial_actions WHERE id = %s", (action_id,))
            cur.execute("DELETE FROM sources WHERE id = %s", (s["id"],))
