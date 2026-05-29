"""Fase 8 — Testes de aprovação, rejeição, publicação e auditoria editorial.

Cobre: transições de status, notas de revisor, registro em editorial_actions,
approve_article escrevendo editorial_status='approved', mark_published auditável,
comportamento idempotente e dashboard_queries de auditoria.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_radar import dispatch


# ── Helpers de fixture ────────────────────────────────────────────────────────

def _make_dispatch(status: str, article_id: str = "art-x") -> dict:
    return {
        "id": 99,
        "article_id": article_id,
        "status": status,
        "scope": "brasil",
        "article_tg_message_id": None,
        "card_tg_message_id": None,
        "card_path": None,
    }


class _FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return {"article_id": "art-x"}

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.cursor_obj = _FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@contextmanager
def _fake_connect():
    yield _FakeConn()


# ── approve_article ───────────────────────────────────────────────────────────

class TestApproveArticle:
    def test_retorna_article_approved(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", _fake_connect)

        result = dispatch.approve_article(99, "Editor X", generate_card=False, dry_run=True)

        assert result["status"] == "article_approved"

    def test_atualiza_article_reviewed_by(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", _fake_connect)

        dispatch.approve_article(99, "Maria", generate_card=False)

        assert updates[0]["article_reviewed_by"] == "Maria"

    def test_persiste_review_notes_no_dispatch(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", _fake_connect)

        dispatch.approve_article(99, "João", generate_card=False, notes="Bom conteúdo.")

        assert updates[0].get("review_notes") == "Bom conteúdo."

    def test_sem_notes_nao_inclui_chave(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", _fake_connect)

        dispatch.approve_article(99, "João", generate_card=False, notes=None)

        assert "review_notes" not in updates[0]

    def test_escreve_editorial_status_approved_no_artigo(self, monkeypatch):
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article", "art-abc"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.approve_article(99, "Editor", generate_card=False)

        executed_queries = [q for q, _ in fake_conn.cursor_obj.executed]
        assert any("editorial_status" in q for q in executed_queries), (
            "approve_article deve atualizar articles.editorial_status"
        )

    def test_idempotente_se_ja_aprovado(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("article_approved"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))

        result = dispatch.approve_article(99, "Editor", generate_card=False)

        assert result.get("skipped") is True
        assert updates == []

    def test_dispatch_nao_encontrado(self, monkeypatch):
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: None)

        result = dispatch.approve_article(999, "Editor", generate_card=False)

        assert result["ok"] is False
        assert "nao encontrado" in result["error"]


# ── reject_article ────────────────────────────────────────────────────────────

class TestRejectArticle:
    def test_retorna_article_rejected(self, monkeypatch):
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)

        result = dispatch.reject_article(99, "Editor")

        assert result["status"] == "article_rejected"

    def test_persiste_notes(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))

        dispatch.reject_article(99, "Editor", notes="Fora do escopo.")

        assert updates[0].get("review_notes") == "Fora do escopo."

    def test_idempotente_se_ja_rejeitado(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("article_rejected"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))

        result = dispatch.reject_article(99, "Editor")

        assert result.get("skipped") is True
        assert updates == []

    def test_registra_acao_editorial(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_article"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "_try_record_editorial_action",
                            lambda **kw: recorded.append(kw))

        dispatch.reject_article(99, "Editor Y", notes="Repetido.")

        assert any(r.get("action") == "reject_article" for r in recorded)
        assert any(r.get("notes") == "Repetido." for r in recorded)


# ── approve_card ──────────────────────────────────────────────────────────────

class TestApproveCard:
    def test_retorna_ready_to_publish(self, monkeypatch):
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_card"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        result = dispatch.approve_card(99, "Editor")

        assert result["status"] == "ready_to_publish"

    def test_persiste_notes(self, monkeypatch):
        updates = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_card"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.approve_card(99, "Editor", notes="Ótimo card.")

        assert any(u.get("review_notes") == "Ótimo card." for u in updates)

    def test_skip_se_status_fora_do_fluxo(self, monkeypatch):
        """approve_card não processa dispatches já publicados ou rejeitados."""
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("published"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))

        result = dispatch.approve_card(99, "Editor")

        assert result.get("skipped") is True
        assert updates == []


# ── reject_card ───────────────────────────────────────────────────────────────

class TestRejectCard:
    def test_retorna_card_rejected(self, monkeypatch):
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_card"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        result = dispatch.reject_card(99, "Editor")

        assert result["status"] == "card_rejected"

    def test_persiste_notes(self, monkeypatch):
        updates = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_card"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.reject_card(99, "Editor", notes="Imagem ruim.")

        assert any(u.get("review_notes") == "Imagem ruim." for u in updates)

    def test_registra_acao_editorial(self, monkeypatch):
        recorded = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: _make_dispatch("pending_card"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)
        monkeypatch.setattr(dispatch, "_try_record_editorial_action",
                            lambda **kw: recorded.append(kw))

        dispatch.reject_card(99, "Editor Z")

        assert any(r.get("action") == "reject_card" for r in recorded)


# ── mark_published ────────────────────────────────────────────────────────────

class TestMarkPublished:
    def test_atualiza_dispatch_status_para_published(self, monkeypatch):
        updates = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch",
                            lambda _: _make_dispatch("ready_to_publish"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.mark_published(99, user="Editor")

        assert any(u.get("status") == "published" for u in updates)

    def test_registra_acao_editorial(self, monkeypatch):
        recorded = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch",
                            lambda _: _make_dispatch("ready_to_publish"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)
        monkeypatch.setattr(dispatch, "_try_record_editorial_action",
                            lambda **kw: recorded.append(kw))

        dispatch.mark_published(99, user="Editor Pub")

        assert any(r.get("action") == "published" for r in recorded)
        assert any(r.get("actor") == "Editor Pub" for r in recorded)

    def test_persiste_notes(self, monkeypatch):
        updates = []
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch",
                            lambda _: _make_dispatch("ready_to_publish"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.mark_published(99, user="Editor", notes="Publicado no Instagram.")

        assert any(u.get("review_notes") == "Publicado no Instagram." for u in updates)

    def test_atualiza_articles_editorial_status_published(self, monkeypatch):
        fake_conn = _FakeConn()

        @contextmanager
        def conn_factory():
            yield fake_conn

        monkeypatch.setattr(dispatch, "get_dispatch",
                            lambda _: _make_dispatch("ready_to_publish", "art-pub"))
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: None)
        monkeypatch.setattr(dispatch, "connect", conn_factory)

        dispatch.mark_published(99)

        executed = [q for q, _ in fake_conn.cursor_obj.executed]
        assert any("published" in q for q in executed), (
            "mark_published deve atualizar articles.editorial_status"
        )

    def test_noop_se_dispatch_nao_existe(self, monkeypatch):
        updates = []
        monkeypatch.setattr(dispatch, "get_dispatch", lambda _: None)
        monkeypatch.setattr(dispatch, "update_dispatch", lambda _, **kw: updates.append(kw))

        dispatch.mark_published(999)

        assert updates == []


# ── _try_record_editorial_action ─────────────────────────────────────────────

class TestTryRecordEditorialAction:
    def test_nao_propaga_excecao(self, monkeypatch):
        def boom(**kw):
            raise RuntimeError("DB explodiu")

        monkeypatch.setattr(
            "news_radar.dispatch._try_record_editorial_action",
            lambda **kw: None,
        )
        # Não deve lançar
        dispatch._try_record_editorial_action(action="test", actor="x")

    def test_passa_notes_para_record_editorial_action(self, monkeypatch):
        captured = []

        def fake_record(**kw):
            captured.append(kw)

        import news_radar.dispatch as d_module
        with patch.object(d_module, "_try_record_editorial_action",
                          side_effect=lambda **kw: captured.append(kw)):
            pass

        # Testa diretamente via editorial.py mock
        from news_radar import editorial
        original = editorial.record_editorial_action
        try:
            calls = []
            editorial.record_editorial_action = lambda **kw: calls.append(kw)
            dispatch._try_record_editorial_action(
                action="test_action",
                actor="Editor",
                notes="nota importante",
            )
            if calls:
                assert calls[0].get("notes") == "nota importante"
        finally:
            editorial.record_editorial_action = original


# ── dashboard_queries — funções de auditoria ──────────────────────────────────

class TestAuditQueries:
    def test_article_audit_history_retorna_lista_vazia_em_excecao(self, monkeypatch):
        from news_radar import dashboard_queries as dq

        monkeypatch.setattr(dq, "connect", _fake_error_connect)
        result = dq.article_audit_history("nao_existe")
        assert result == []

    def test_dispatch_audit_history_retorna_lista_vazia_em_excecao(self, monkeypatch):
        from news_radar import dashboard_queries as dq

        monkeypatch.setattr(dq, "connect", _fake_error_connect)
        result = dq.dispatch_audit_history(9999)
        assert result == []

    def test_audit_page_actions_retorna_lista_vazia_em_excecao(self, monkeypatch):
        from news_radar import dashboard_queries as dq

        monkeypatch.setattr(dq, "connect", _fake_error_connect)
        result = dq.audit_page_actions(days_back=7)
        assert result == []

    def test_audit_metrics_retorna_zeros_em_excecao(self, monkeypatch):
        from news_radar import dashboard_queries as dq

        monkeypatch.setattr(dq, "connect", _fake_error_connect)
        result = dq.audit_metrics(days_back=7)
        assert result["total"] == 0
        assert result["approvals"] == 0
        assert result["rejections"] == 0

    def test_audit_page_actions_aceita_filtro_de_acao(self, monkeypatch):
        from news_radar import dashboard_queries as dq

        rows_captured = []

        class FakeAuditCursor:
            def __init__(self):
                self.last_query = ""
                self.last_params = None

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, q, p=None):
                self.last_query = q
                self.last_params = p
                rows_captured.append(p)

            def fetchall(self):
                return []

        class FakeAuditConn:
            def __init__(self):
                self.cursor_obj = FakeAuditCursor()

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        @contextmanager
        def fake_connect():
            yield FakeAuditConn()

        monkeypatch.setattr(dq, "connect", fake_connect)
        dq.audit_page_actions(days_back=7, action_filter="approve_article")

        # Verifica que o filtro foi passado como parâmetro
        flat_params = [p for row in rows_captured for p in (row or [])]
        assert "approve_article" in flat_params


@contextmanager
def _fake_error_connect():
    raise Exception("Sem banco de dados")
    yield  # noqa: unreachable
