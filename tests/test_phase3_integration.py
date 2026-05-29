"""
Testes de integração da Fase 3 — Dashboard Cockpit Inicial.

Verifica:
  1. collector._try_update_source_status() — delega a mark_source_success/error quando fonte existe.
  2. dispatch._try_record_editorial_action() — registra ação sem quebrar o fluxo.
  3. approve_article() — chama _try_record_editorial_action com parâmetros corretos.
  4. reject_article() — idem.
  5. dashboard_queries.sources_summary() — retorna zeros quando banco vazio ou ausente.
  6. dashboard_queries.recent_editorial_actions() — retorna lista vazia em caso de erro.

Ref: specs/08-editorial-dashboard.md, specs/10-approval-publication.md,
     specs/03-ingestion-sources.md, specs/11-audit-observability.md
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import news_radar.collector as collector_module
import news_radar.dispatch as dispatch_module


# ===========================================================================
# Helpers de mock (mesmo padrão das fases anteriores)
# ===========================================================================

class _FakeCursor:
    def __init__(self, one=None, rows=None):
        self._one = one
        self._rows = rows or []
        self.executed: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, q, p=None):
        self.executed.append((q, p or ()))

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


def _mk_connect(cur):
    @contextmanager
    def _connect():
        yield _FakeConn(cur)
    return _connect


# ===========================================================================
# Testes de collector._try_update_source_status
# ===========================================================================

def test_try_update_source_status_chama_mark_success_quando_status_ok(monkeypatch):
    """_try_update_source_status chama mark_source_success quando status='ok' e fonte existe."""
    src_row = {"id": 7, "name": "G1"}

    called_success = []
    called_error = []

    monkeypatch.setattr(
        "news_radar.sources.get_source_by_name",
        lambda name: src_row,
    )
    monkeypatch.setattr(
        "news_radar.sources.mark_source_success",
        lambda sid, collected_count=0: called_success.append(sid),
    )
    monkeypatch.setattr(
        "news_radar.sources.mark_source_error",
        lambda sid, error_msg="": called_error.append(sid),
    )

    collector_module._try_update_source_status("G1", "ok", 10, None)

    assert called_success == [7]
    assert called_error == []


def test_try_update_source_status_chama_mark_error_quando_status_error(monkeypatch):
    """_try_update_source_status chama mark_source_error quando status='error' e fonte existe."""
    src_row = {"id": 3, "name": "CNN Brasil"}

    called_error = []

    monkeypatch.setattr("news_radar.sources.get_source_by_name", lambda name: src_row)
    monkeypatch.setattr("news_radar.sources.mark_source_success", lambda sid, **kw: None)
    monkeypatch.setattr(
        "news_radar.sources.mark_source_error",
        lambda sid, error_msg="": called_error.append((sid, error_msg)),
    )

    collector_module._try_update_source_status("CNN Brasil", "error", 0, "Timeout")

    assert called_error == [(3, "Timeout")]


def test_try_update_source_status_ignora_fonte_nao_cadastrada(monkeypatch):
    """_try_update_source_status não faz nada quando fonte não está na tabela sources."""
    called_success = []
    called_error = []

    monkeypatch.setattr("news_radar.sources.get_source_by_name", lambda name: None)
    monkeypatch.setattr(
        "news_radar.sources.mark_source_success",
        lambda sid, **kw: called_success.append(sid),
    )
    monkeypatch.setattr(
        "news_radar.sources.mark_source_error",
        lambda sid, **kw: called_error.append(sid),
    )

    collector_module._try_update_source_status("Fonte Desconhecida", "ok", 5, None)

    assert called_success == []
    assert called_error == []


def test_try_update_source_status_warning_trata_como_sucesso(monkeypatch):
    """_try_update_source_status trata 'warning' como sucesso (bozo_exception é aceitável)."""
    src_row = {"id": 9, "name": "Veja"}
    called_success = []

    monkeypatch.setattr("news_radar.sources.get_source_by_name", lambda name: src_row)
    monkeypatch.setattr(
        "news_radar.sources.mark_source_success",
        lambda sid, collected_count=0: called_success.append(sid),
    )
    monkeypatch.setattr("news_radar.sources.mark_source_error", lambda sid, **kw: None)

    collector_module._try_update_source_status("Veja", "warning", 5, "bozo")

    assert called_success == [9]


def test_try_update_source_status_nao_propaga_excecao(monkeypatch):
    """_try_update_source_status absorve exceções sem quebrar a coleta."""
    monkeypatch.setattr(
        "news_radar.sources.get_source_by_name",
        lambda name: (_ for _ in ()).throw(RuntimeError("DB offline")),
    )

    # Não deve lançar exceção
    collector_module._try_update_source_status("Qualquer", "ok", 5, None)


# ===========================================================================
# Testes de dispatch._try_record_editorial_action
# ===========================================================================

def test_try_record_editorial_action_chama_record(monkeypatch):
    """_try_record_editorial_action delega para editorial.record_editorial_action."""
    chamadas = []

    monkeypatch.setattr(
        "news_radar.editorial.record_editorial_action",
        lambda action, actor, **kw: chamadas.append((action, actor, kw)),
    )

    # Precisa recarregar o import lazy dentro do helper
    with patch("news_radar.editorial.record_editorial_action") as mock_rec:
        mock_rec.return_value = 1
        dispatch_module._try_record_editorial_action(
            action="approve_article",
            actor="Editor",
            article_id="abc",
            dispatch_id=5,
            from_status="pending_article",
            to_status="article_approved",
        )
        mock_rec.assert_called_once_with(
            action="approve_article",
            actor="Editor",
            article_id="abc",
            dispatch_id=5,
            from_status="pending_article",
            to_status="article_approved",
        )


def test_try_record_editorial_action_nao_propaga_excecao(monkeypatch):
    """_try_record_editorial_action absorve exceção sem quebrar o dispatch."""
    with patch("news_radar.editorial.record_editorial_action") as mock_rec:
        mock_rec.side_effect = RuntimeError("editorial_actions indisponível")

        # Não deve lançar exceção
        dispatch_module._try_record_editorial_action(
            action="approve_article",
            actor="Editor",
        )


# ===========================================================================
# Testes de approve_article e reject_article integrados
# ===========================================================================

def _fake_dispatch_row(status="pending_article"):
    return {
        "id": 1,
        "article_id": "art-x",
        "status": status,
        "article_tg_message_id": None,
        "card_tg_message_id": None,
        "scope": "brasil",
    }


def test_approve_article_chama_try_record(monkeypatch):
    """approve_article() chama _try_record_editorial_action após update_dispatch."""
    monkeypatch.setattr(dispatch_module, "get_dispatch", lambda _id: _fake_dispatch_row())
    monkeypatch.setattr(dispatch_module, "update_dispatch", lambda _id, **kw: None)
    monkeypatch.setattr(dispatch_module, "_edit_article_message", lambda *a, **kw: None)
    monkeypatch.setattr(
        dispatch_module, "generate_card_for_dispatch",
        lambda dispatch_id, user="Editor", **kw: {"ok": True},
    )

    recorded = []
    monkeypatch.setattr(
        dispatch_module,
        "_try_record_editorial_action",
        lambda action, actor, **kw: recorded.append((action, actor)),
    )

    dispatch_module.approve_article(1, user="Revisor", generate_card=False)

    assert any(r[0] == "approve_article" for r in recorded), (
        "approve_article() deve chamar _try_record_editorial_action com action='approve_article'"
    )
    assert any(r[1] == "Revisor" for r in recorded), (
        "actor deve ser o usuário passado para approve_article()"
    )


def test_reject_article_chama_try_record(monkeypatch):
    """reject_article() chama _try_record_editorial_action após update_dispatch."""
    monkeypatch.setattr(dispatch_module, "get_dispatch", lambda _id: _fake_dispatch_row())
    monkeypatch.setattr(dispatch_module, "update_dispatch", lambda _id, **kw: None)
    monkeypatch.setattr(dispatch_module, "_edit_article_message", lambda *a, **kw: None)

    recorded = []
    monkeypatch.setattr(
        dispatch_module,
        "_try_record_editorial_action",
        lambda action, actor, **kw: recorded.append((action, actor)),
    )

    dispatch_module.reject_article(1, user="Revisor")

    assert any(r[0] == "reject_article" for r in recorded)
    assert any(r[1] == "Revisor" for r in recorded)


def test_approve_article_skipped_nao_chama_record(monkeypatch):
    """Se dispatch não está em pending_article, approve_article retorna sem registrar ação."""
    monkeypatch.setattr(
        dispatch_module, "get_dispatch",
        lambda _id: _fake_dispatch_row(status="article_approved"),  # já aprovado
    )

    recorded = []
    monkeypatch.setattr(
        dispatch_module,
        "_try_record_editorial_action",
        lambda action, actor, **kw: recorded.append(action),
    )

    result = dispatch_module.approve_article(1, user="Editor", generate_card=False)

    assert result.get("skipped") is True
    assert recorded == [], "Não deve registrar ação se dispatch já foi processado"


# ===========================================================================
# Testes de dashboard_queries.sources_summary e recent_editorial_actions
# ===========================================================================

def test_sources_summary_retorna_zeros_em_excecao(monkeypatch):
    """sources_summary() retorna estrutura de zeros se banco não disponível."""
    import news_radar.dashboard_queries as dq

    monkeypatch.setattr(dq, "connect", lambda: (_ for _ in ()).throw(Exception("DB down")))

    result = dq.sources_summary()

    assert result["total"] == 0
    assert result["enabled"] == 0
    assert result["with_error"] == 0
    assert isinstance(result["by_scope"], dict)


def test_recent_editorial_actions_retorna_lista_vazia_em_excecao(monkeypatch):
    """recent_editorial_actions() retorna [] se banco não disponível."""
    import news_radar.dashboard_queries as dq

    monkeypatch.setattr(dq, "connect", lambda: (_ for _ in ()).throw(Exception("DB down")))

    result = dq.recent_editorial_actions()

    assert result == []


def test_sources_summary_com_mock_de_banco(monkeypatch):
    """sources_summary() agrupa dados corretamente a partir de linhas mockadas."""
    import news_radar.dashboard_queries as dq

    cur = _FakeCursor(
        one={"total": 57, "enabled": 55, "with_error": 3},
        rows=[
            {"scope": "brasil", "n": 30},
            {"scope": "piaui", "n": 15},
            {"scope": "teresina", "n": 12},
        ],
    )
    monkeypatch.setattr(dq, "connect", _mk_connect(cur))

    result = dq.sources_summary()

    assert result["total"] == 57
    assert result["enabled"] == 55
    assert result["with_error"] == 3
    assert result["by_scope"]["brasil"] == 30
    assert result["by_scope"]["teresina"] == 12
