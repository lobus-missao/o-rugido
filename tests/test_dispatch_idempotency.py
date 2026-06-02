"""
Testes de idempotência para create_dispatch().

Verifica que chamadas repetidas para a mesma edição/data/scope não resultam
em duplicação de dispatches ou envios duplicados ao Telegram.

Ref: docs/specs/12-n8n-decoupling.md — "Prevenção de duplo disparo"
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

from news_radar.services import editorial as dispatch


# ---------------------------------------------------------------------------
# Helpers de mock
# ---------------------------------------------------------------------------


class _CntCursor:
    """Cursor que retorna cnt configurável para a query do guard de idempotência."""

    def __init__(self, cnt: int):
        self._cnt = cnt

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return {"cnt": self._cnt}

    def fetchall(self):
        return []


class _CntConn:
    def __init__(self, cnt: int):
        self._cnt = cnt

    def cursor(self):
        return _CntCursor(self._cnt)


def _mock_connect(cnt: int):
    """Factory: retorna context manager de conexão que reporta `cnt` dispatches ativos."""

    @contextmanager
    def _connect():
        yield _CntConn(cnt)

    return _connect


# ---------------------------------------------------------------------------
# Testes do guard de idempotência
# ---------------------------------------------------------------------------


def test_guard_blocks_when_active_dispatch_exists(monkeypatch):
    """Guard retorna [] e não chama select_top_articles quando já há dispatch ativo."""
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=2))

    select_called = []
    monkeypatch.setattr(
        dispatch, "select_top_articles",
        lambda *a, **kw: select_called.append(1) or [],
    )

    result = dispatch.create_dispatch("default", scope="piaui", top=3, dry_run=True)

    assert result == [], "Guard deve retornar [] quando edição ativa já existe"
    assert select_called == [], "select_top_articles não deve ser chamada quando guard bloqueia"


def test_guard_allows_when_no_active_dispatches(monkeypatch):
    """Guard não bloqueia quando cnt=0 — select_top_articles é chamada normalmente."""
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=0))

    select_called = []
    monkeypatch.setattr(
        dispatch, "select_top_articles",
        # retorna [] para encerrar create_dispatch cedo (sem INSERT/Telegram)
        lambda *a, **kw: select_called.append(1) or [],
    )

    dispatch.create_dispatch("default", scope="piaui", top=3, dry_run=True)

    assert select_called, "select_top_articles deve ser chamada quando guard não bloqueia"


def test_guard_allows_when_all_dispatches_rejected(monkeypatch):
    """Nova edição é permitida quando todos os dispatches anteriores foram rejeitados.

    O SQL do guard filtra status NOT IN ('article_rejected', 'card_rejected'),
    então se todos foram rejeitados cnt=0 e o guard não bloqueia.
    """
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=0))

    select_called = []
    monkeypatch.setattr(
        dispatch, "select_top_articles",
        lambda *a, **kw: select_called.append(1) or [],
    )

    dispatch.create_dispatch("default", scope="piaui", top=3, dry_run=True)

    assert select_called, "Nova edição deve ser permitida quando todos os dispatches foram rejeitados"


def test_guard_invalid_edition_raises_before_db_access(monkeypatch):
    """Edition inválida lança ValueError antes de qualquer acesso ao banco."""
    connect_called = []

    @contextmanager
    def _sentinel_connect():
        connect_called.append(1)
        yield _CntConn(0)

    monkeypatch.setattr(dispatch, "connect", _sentinel_connect)

    with pytest.raises(ValueError, match="edition deve ser"):
        dispatch.create_dispatch("invalid_edition", scope="piaui", top=3)

    assert connect_called == [], "connect() não deve ser chamado para edition inválida"


def test_guard_logs_warning_when_blocked(monkeypatch, caplog):
    """Guard registra warning com contexto claro quando dispatch duplicado é bloqueado."""
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=1))
    monkeypatch.setattr(dispatch, "select_top_articles", lambda *a, **kw: [])

    with caplog.at_level(logging.WARNING, logger="news_radar.services.editorial"):
        result = dispatch.create_dispatch("default", scope="piaui", top=3, dry_run=True)

    assert result == []
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_messages, "Nenhum warning foi registrado pelo guard"
    assert any("bloqueado" in m.lower() or "idempot" in m.lower() for m in warning_messages), (
        f"Warning não menciona bloqueio/idempotência: {warning_messages}"
    )


def test_guard_scope_isolation(monkeypatch):
    """Guard é isolado por scope: mesma edição com scope diferente não é bloqueada.

    Cenário: morning/piaui existe (cnt=1 para piaui), mas morning/brasil
    não existe (cnt=0 para brasil). O mock aqui simula cnt=0 para provar
    que o path sem bloqueio funciona — o teste de isolation real requer banco.
    """
    # Simula consulta que retorna 0 (scope diferente não conflita)
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=0))

    select_called = []
    monkeypatch.setattr(
        dispatch, "select_top_articles",
        lambda *a, **kw: select_called.append(1) or [],
    )

    dispatch.create_dispatch("default", scope="brasil", top=3, dry_run=True)

    assert select_called, "Edição com scope diferente deve ser processada"


def test_guard_returns_empty_list_type(monkeypatch):
    """Retorno do guard quando bloqueado é sempre list, nunca None."""
    monkeypatch.setattr(dispatch, "connect", _mock_connect(cnt=5))
    monkeypatch.setattr(dispatch, "select_top_articles", lambda *a, **kw: [])

    result = dispatch.create_dispatch("default", scope="piaui", top=3, dry_run=True)

    assert isinstance(result, list), "create_dispatch deve retornar list mesmo quando bloqueado"
    assert len(result) == 0
