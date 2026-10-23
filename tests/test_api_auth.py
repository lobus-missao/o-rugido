"""Autenticação server-to-server da API (X-Internal-Key)."""
from __future__ import annotations

import pytest

import api_server
from o_rugido.api import auth
from o_rugido.api.routes import ingestion as ingestion_route

KEY = "chave-de-teste-123"

# (método, caminho) das rotas de automação que passam a exigir a chave.
PROTECTED = [
    ("get", "/stats"),
    ("post", "/pipeline/collect"),
    ("post", "/pipeline/rank"),
    ("post", "/pipeline/cleanup"),
    ("post", "/cards/render"),
    ("get", "/dispatch/1/edit-token"),
    ("get", "/monitor/api"),
    ("get", "/monitor/telegram"),
    ("get", "/monitor/all"),
    ("post", "/monitor/dispatch-alerts"),
]


@pytest.fixture
def client():
    return api_server.app.test_client()


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", KEY)


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    """Garante que nenhuma rota protegida chegue ao banco/serviços nos testes."""
    monkeypatch.setattr(ingestion_route, "stats", lambda: {"total_articles": 0})
    monkeypatch.setattr(ingestion_route, "rank_all", lambda only_unscored=True: 0)
    monkeypatch.setattr(ingestion_route, "collect_feeds", lambda limit_per_feed=30: {})


class TestSemChaveConfigurada:
    """Sem INTERNAL_API_KEY o comportamento é o antigo (não quebra o n8n)."""

    def test_rotas_continuam_abertas(self, client, no_key):
        assert client.get("/stats").status_code == 200
        assert client.post("/pipeline/rank").status_code == 200

    def test_header_enviado_sem_chave_configurada_tambem_passa(self, client, no_key):
        resp = client.get("/stats", headers={auth.HEADER: "qualquer"})
        assert resp.status_code == 200


class TestComChaveConfigurada:
    @pytest.mark.parametrize(("method", "path"), PROTECTED)
    def test_sem_header_retorna_401(self, client, with_key, method, path):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401
        assert resp.get_json() == {"ok": False, "error": "unauthorized"}

    @pytest.mark.parametrize(("method", "path"), PROTECTED)
    def test_chave_errada_retorna_401(self, client, with_key, method, path):
        resp = getattr(client, method)(path, headers={auth.HEADER: "errada"})
        assert resp.status_code == 401

    def test_chave_vazia_retorna_401(self, client, with_key):
        resp = client.get("/stats", headers={auth.HEADER: ""})
        assert resp.status_code == 401

    def test_chave_correta_passa(self, client, with_key):
        resp = client.get("/stats", headers={auth.HEADER: KEY})
        assert resp.status_code == 200
        assert resp.get_json()["total_articles"] == 0

    def test_post_com_chave_correta_passa(self, client, with_key):
        resp = client.post("/pipeline/rank", headers={auth.HEADER: KEY})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_cleanup_sem_chave_nao_toca_no_banco(self, client, with_key, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("cleanup chegou ao banco sem autenticacao")

        monkeypatch.setattr(ingestion_route, "connect", boom)
        resp = client.post("/pipeline/cleanup", json={"days": 0})
        assert resp.status_code == 401

    def test_chave_com_caracteres_nao_ascii_nao_quebra(self, client, with_key):
        resp = client.get("/stats", headers={auth.HEADER: "çhave-ñ"})
        assert resp.status_code == 401


class TestRotasPublicasContinuamPublicas:
    """Rotas que precisam seguir abertas mesmo com a chave configurada."""

    def test_health(self, client, with_key):
        assert client.get("/health").status_code == 200

    def test_card_servido_para_o_instagram(self, client, with_key):
        # arquivo inexistente: 404 do handler, e não 401 do auth
        assert client.get("/cards/nao-existe.png").status_code == 404

    def test_pagina_de_edicao_usa_token_proprio(self, client, with_key):
        # token inválido: 404 da própria página, e não 401
        resp = client.get("/edit?token=invalido")
        assert resp.status_code != 401

    def test_image_search_chamado_pelo_navegador(self, client, with_key):
        # sem q: 400 de validação da rota, e não 401
        assert client.get("/api/image-search").status_code == 400

    def test_rota_inexistente_continua_404(self, client, with_key):
        assert client.get("/nao-existe").status_code == 404


def test_endpoints_publicos_existem_na_app():
    """Se uma rota pública for renomeada, o auth passaria a bloqueá-la em silêncio."""
    registrados = {rule.endpoint for rule in api_server.app.url_map.iter_rules()}
    assert registrados >= auth.PUBLIC_ENDPOINTS
