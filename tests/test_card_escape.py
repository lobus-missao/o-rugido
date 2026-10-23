"""Escape de HTML no card, bloqueio de rede do Chromium e redação do token."""
from __future__ import annotations

import re

import pytest
import requests

from o_rugido.core.text_utils import redact_secret
from o_rugido.services import editorial, monitoring, rendering
from o_rugido.services.rendering import (
    _allow_only_inline,
    build_card_context,
    list_templates,
    render_card_html,
)

PAYLOADS = [
    '<script>alert(1)</script>',
    '<img src="http://169.254.169.254/latest/meta-data/" onerror="alert(1)">',
    '"><iframe src="http://127.0.0.1:8888/stats"></iframe>',
    "<link rel=stylesheet href=http://127.0.0.1:8888/x.css>",
    "' onmouseover='alert(1)",
]


def _article(**over):
    base = {
        "id": "xss0001xss0002xss0",
        "title": "Titulo normal",
        "source": "Fonte",
        "source_scope": "piaui",
        "summary": "Resumo normal com mais de cinquenta caracteres para o teste do card.",
        "priority": "alta",
        "category": "Geral",
        "locality": "Teresina",
        "published_at": "2026-05-29",
        "url": "https://exemplo.com/a",
    }
    base.update(over)
    return base


class TestEscape:
    @pytest.mark.parametrize("payload", PAYLOADS)
    @pytest.mark.parametrize("campo", ["title", "source", "summary", "category", "locality", "url"])
    @pytest.mark.parametrize("template", list_templates())
    def test_payload_nunca_vira_tag(self, template, campo, payload):
        html = render_card_html(_article(**{campo: payload}), template_name=template)
        for marca in ("<script", "<iframe", "<link rel=stylesheet", "<img src=\"http://169", "onerror=\"", "<img src=\"http://"):
            assert marca not in html.replace('<img src="data:', ""), f"{campo}/{template}: {marca}"

    @pytest.mark.parametrize("payload", PAYLOADS)
    def test_overrides_do_editor_tambem_escapam(self, payload):
        ctx = build_card_context(_article(), title_override=payload, subtitle_override=payload)
        assert "<" not in ctx["titulo"]
        assert "<" not in ctx["subtitulo_html"].replace('<div class="card-subtitulo">', "").replace("</div>", "")

    def test_override_de_resumo_escapa(self):
        ctx = build_card_context(_article(__summary_override="<b>x</b>"))
        assert "<b>" not in ctx["resumo"]

    def test_url_de_imagem_nao_quebra_atributo(self):
        ctx = build_card_context(_article(), image_url='http://x.test/a.png" onerror="alert(1)')
        assert '"' not in ctx["image_url"]

    def test_texto_legitimo_continua_legivel(self):
        ctx = build_card_context(_article(title="Ações & Obras: \u2018Teresina\u2019 — R$ 5 mi", category="Saúde"))
        assert ctx["titulo"] == "Ações &amp; Obras: \u2018Teresina\u2019 — R$ 5 mi"
        assert ctx["editoria"] == "Saúde"

    def test_acentos_nao_viram_entidade(self):
        ctx = build_card_context(_article(title="Educação, ônibus e coração"))
        assert ctx["titulo"] == "Educação, ônibus e coração"

    def test_html_estrutural_do_proprio_codigo_nao_e_escapado(self):
        ctx = build_card_context(_article())
        assert ctx["categoria_tag"].startswith('<span class="tag tag-categoria">')
        assert ctx["localidade_tag"].startswith('<span class="tag local">')
        assert ctx["conteudo_tag"].startswith('<span class="tag')

    def test_sem_placeholders_crus(self):
        html = render_card_html(_article(title="{{resumo}} <b>x</b>"))
        assert "<b>x</b>" not in html


class _Route:
    def __init__(self, url):
        self.request = type("R", (), {"url": url})()
        self.acao = None

    def continue_(self):
        self.acao = "continue"

    def abort(self):
        self.acao = "abort"


class TestChromiumSemRede:
    @pytest.mark.parametrize("url", [
        "data:image/png;base64,AAAA", "about:blank", "data:text/html,<p>x</p>",
    ])
    def test_inline_passa(self, url):
        r = _Route(url)
        _allow_only_inline(r)
        assert r.acao == "continue"

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8888/stats", "https://example.com/x.png", "http://169.254.169.254/",
        "file:///etc/passwd", "ftp://x/y", "ws://localhost:1/", "chrome://version",
    ])
    def test_todo_o_resto_e_abortado(self, url):
        r = _Route(url)
        _allow_only_inline(r)
        assert r.acao == "abort"

    def test_render_single_card_registra_o_bloqueio(self):
        import inspect

        src = inspect.getsource(rendering.render_single_card)
        assert 'page.route("**/*", _allow_only_inline)' in src
        # a rota precisa ser registrada ANTES do set_content
        assert src.index("page.route(") < src.index("page.set_content(")


TOKEN = "123456:ABC-DEF_tokenSECRETO"


class TestTokenNaoVaza:
    def test_redact_secret(self):
        assert redact_secret(f"erro em /bot{TOKEN}/getMe", TOKEN) == "erro em /bot***/getMe"
        assert redact_secret("sem segredo", TOKEN) == "sem segredo"
        assert redact_secret("abc", "") == "abc"
        assert redact_secret("abc", None) == "abc"

    def test_telegram_health_nao_devolve_token(self, monkeypatch):
        def boom(url, **k):
            raise requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/getMe")

        monkeypatch.setattr(monitoring.requests, "get", boom)
        result = monitoring.telegram_health(TOKEN)
        assert result["ok"] is False
        assert TOKEN not in str(result)
        assert "tokenSECRETO" not in str(result)

    def test_token_no_fim_da_mensagem_nao_sobra_pedaco(self, monkeypatch):
        # a redação acontece ANTES do corte em 150 chars
        def boom(url, **k):
            raise requests.ConnectionError("x" * 140 + TOKEN)

        monkeypatch.setattr(monitoring.requests, "get", boom)
        assert "tokenSECRETO" not in monitoring.telegram_health(TOKEN)["error"]
        assert "123456:ABC" not in monitoring.telegram_health(TOKEN)["error"]

    def test_tg_redige_token_e_preserva_o_tipo_da_excecao(self, monkeypatch):
        monkeypatch.delenv("O_RUGIDO_DRY_RUN", raising=False)
        monkeypatch.setattr(editorial, "TELEGRAM_BOT_TOKEN", TOKEN)
        monkeypatch.setattr(editorial, "API", f"https://api.telegram.org/bot{TOKEN}")

        def boom(url, **k):
            raise requests.HTTPError(f"400 Client Error: Bad Request for url: {url}")

        monkeypatch.setattr(editorial.requests, "post", boom)
        with pytest.raises(requests.HTTPError) as info:
            editorial._tg("sendMessage", json={})
        assert TOKEN not in str(info.value)
        assert re.search(r"/bot\*\*\*/sendMessage", str(info.value))

    def test_tg_sem_erro_continua_funcionando(self, monkeypatch):
        monkeypatch.delenv("O_RUGIDO_DRY_RUN", raising=False)
        monkeypatch.setattr(editorial, "TELEGRAM_BOT_TOKEN", TOKEN)

        class Ok:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True, "result": {"message_id": 7}}

        monkeypatch.setattr(editorial.requests, "post", lambda url, **k: Ok())
        assert editorial._tg("sendMessage", json={})["result"]["message_id"] == 7
