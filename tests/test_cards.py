"""Testes de geração de card editorial via HTML/PNG.

Cobre: build_card_context, render_card_html, save_card_html, list_templates,
validação de dados obrigatórios, overrides e ausência de placeholders crus.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_radar.services.rendering import (
    _render_html,
    build_card_context,
    list_templates,
    render_card_html,
    save_card_html,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

ARTICLE_FULL = {
    "id": "abc123def456789012",
    "title": "Prefeitura de Teresina anuncia pacote de obras",
    "url": "https://exemplo.com/obras",
    "canonical_url": "https://exemplo.com/obras",
    "source": "Cidade Verde",
    "source_scope": "teresina",
    "source_trust": 0.74,
    "published_at": "2026-05-29T10:00:00+00:00",
    "summary": "A Prefeitura de Teresina abriu licitação para obras de recapeamento. " * 5,
    "priority": "alta",
    "category": "Governos e politica",
    "final_score_piaui": 71.0,
    "locality": "Teresina",
}

ARTICLE_MINIMAL = {
    "id": "min001min002min003",
    "title": "Evento ocorre amanhã em Teresina",
    "source": "Portal PI",
    "source_scope": "piaui",
    "final_score_piaui": 40.0,
}

ARTICLE_MEDIA = {
    "id": "med0001med0002med0",
    "title": "Artigo de prioridade média",
    "source": "G1 PI",
    "source_scope": "brasil",
    "summary": "Um resumo simples mas com mais de cinquenta caracteres para testar o conteudo_tag.",
    "priority": "media",
    "category": "Geral",
    "final_score_piaui": 45.0,
    "published_at": "2026-05-28",
}

RAW_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}")


# ── Testes: build_card_context ────────────────────────────────────────────────

class TestBuildCardContext:
    def test_titulo_usa_title_do_artigo(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["titulo"] == ARTICLE_FULL["title"]

    def test_titulo_fallback_para_title(self):
        ctx = build_card_context(ARTICLE_MINIMAL)
        assert ctx["titulo"] == ARTICLE_MINIMAL["title"]

    def test_title_override_tem_prioridade(self):
        ctx = build_card_context(ARTICLE_FULL, title_override="Título Manual")
        assert ctx["titulo"] == "Título Manual"

    def test_subtitle_override_aparece(self):
        ctx = build_card_context(ARTICLE_FULL, subtitle_override="Sub manual")
        assert "Sub manual" in ctx["subtitulo_html"]

    def test_subtitulo_html_vazio_sem_override(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["subtitulo_html"] == ""

    def test_prioridade_label_alta(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["prioridade"] == "ALTA"

    def test_prioridade_label_media(self):
        ctx = build_card_context(ARTICLE_MEDIA)
        assert ctx["prioridade"] == "MEDIA"

    def test_prioridade_cor_alta(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["prioridade_cor"] == "#ea580c"

    def test_prioridade_cor_desconhecida_usa_default(self):
        art = {**ARTICLE_MINIMAL, "priority": "desconhecida"}
        ctx = build_card_context(art)
        assert ctx["prioridade_cor"] == "#6b7280"

    def test_categoria_tag_gerada_com_categoria(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert "tag-categoria" in ctx["categoria_tag"]
        assert "Governos" in ctx["categoria_tag"]

    def test_categoria_tag_vazia_para_hifen(self):
        art = {**ARTICLE_MINIMAL, "category": "-"}
        ctx = build_card_context(art)
        assert ctx["categoria_tag"] == ""

    def test_localidade_de_locality(self):
        art = {**ARTICLE_MINIMAL, "locality": "Parnaíba"}
        ctx = build_card_context(art)
        assert "Parnaíba" in ctx["localidade_tag"]

    def test_summary_override_via_magic_key(self):
        art = {**ARTICLE_FULL, "__summary_override": "Resumo editado pela editora"}
        ctx = build_card_context(art)
        assert "Resumo editado" in ctx["resumo"]

    def test_resumo_truncado_a_200_chars(self):
        art = {**ARTICLE_MINIMAL, "summary": "X" * 300}
        ctx = build_card_context(art)
        assert len(ctx["resumo"]) <= 200

    def test_nenhum_valor_e_none(self):
        ctx = build_card_context(ARTICLE_MINIMAL)
        for key, val in ctx.items():
            assert val is not None, f"Chave '{key}' retornou None"

    def test_nenhum_valor_tem_placeholder_cru(self):
        ctx = build_card_context(ARTICLE_FULL)
        for key, val in ctx.items():
            assert not RAW_PLACEHOLDER_PATTERN.search(val), (
                f"Valor da chave '{key}' contém placeholder cru: {val[:80]}"
            )


# ── Testes: render_card_html ──────────────────────────────────────────────────

@pytest.mark.skipif(
    not (TEMPLATES_DIR / "card.html").exists(),
    reason="card.html não encontrado",
)
class TestRenderCardHtml:
    def test_renderiza_sem_placeholders_crus_card_html(self):
        html = render_card_html(ARTICLE_FULL)
        assert not RAW_PLACEHOLDER_PATTERN.search(html)

    def test_renderiza_sem_placeholders_crus_base_html(self):
        base = TEMPLATES_DIR / "card-editorial-base.html"
        if not base.exists():
            pytest.skip("card-editorial-base.html não encontrado")
        html = render_card_html(ARTICLE_FULL, template_name="card-editorial-base.html")
        assert not RAW_PLACEHOLDER_PATTERN.search(html)

    def test_titulo_aparece_no_html(self):
        html = render_card_html(ARTICLE_FULL)
        assert "Prefeitura de Teresina" in html

    def test_title_override_aparece_no_html(self):
        html = render_card_html(
            ARTICLE_FULL, title_override="Título Personalizado Teste"
        )
        assert "Título Personalizado Teste" in html

    def test_fonte_aparece_no_html(self):
        html = render_card_html(ARTICLE_FULL)
        assert "Cidade Verde" in html

    def test_data_aparece_no_html(self):
        html = render_card_html(ARTICLE_FULL)
        assert "2026-05-29" in html

    def test_raise_sem_titulo(self):
        art = {**ARTICLE_FULL, "title": ""}
        with pytest.raises(ValueError, match="titulo"):
            render_card_html(art)

    def test_raise_sem_source(self):
        art = {**ARTICLE_FULL, "source": ""}
        with pytest.raises(ValueError, match="fonte"):
            render_card_html(art)

    def test_raise_template_inexistente(self):
        with pytest.raises(FileNotFoundError):
            render_card_html(ARTICLE_FULL, template_name="nao_existe.html")

    def test_artigo_minimal_sem_placeholders_crus(self):
        html = render_card_html(ARTICLE_MINIMAL)
        assert not RAW_PLACEHOLDER_PATTERN.search(html)

    def test_subtitulo_override_aparece_no_base_template(self):
        base = TEMPLATES_DIR / "card-editorial-base.html"
        if not base.exists():
            pytest.skip("card-editorial-base.html não encontrado")
        html = render_card_html(
            ARTICLE_FULL,
            template_name="card-editorial-base.html",
            subtitle_override="Investimento previsto de R$ 12 milhões",
        )
        assert "Investimento previsto de R$ 12 milhões" in html

    def test_card_html_contem_div_card(self):
        html = render_card_html(ARTICLE_FULL)
        assert 'id="card"' in html


# ── Testes: save_card_html ────────────────────────────────────────────────────

class TestSaveCardHtml:
    def test_salva_arquivo_html(self, tmp_path, monkeypatch):
        import news_radar.services.rendering as cr

        monkeypatch.setattr(cr, "CARDS_DIR", tmp_path)

        html_content = "<html><body>Test card</body></html>"
        art_id = "testid12345678901234"
        path = save_card_html(art_id, html_content)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == html_content

    def test_nome_do_arquivo_usa_16_chars_do_id(self, tmp_path, monkeypatch):
        import news_radar.services.rendering as cr

        monkeypatch.setattr(cr, "CARDS_DIR", tmp_path)
        art_id = "abcdef1234567890xyz"
        path = save_card_html(art_id, "<html/>")
        assert path.name == f"card_{art_id[:16]}.html"

    def test_sobrescreve_arquivo_existente(self, tmp_path, monkeypatch):
        import news_radar.services.rendering as cr

        monkeypatch.setattr(cr, "CARDS_DIR", tmp_path)
        art_id = "overwrite12345678"
        save_card_html(art_id, "versão 1")
        path = save_card_html(art_id, "versão 2")
        assert path.read_text(encoding="utf-8") == "versão 2"


# ── Testes: list_templates ────────────────────────────────────────────────────

class TestListTemplates:
    def test_retorna_lista_nao_vazia(self):
        templates = list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_card_html_esta_na_lista(self):
        if (TEMPLATES_DIR / "card.html").exists():
            assert "card.html" in list_templates()

    def test_apenas_card_templates(self):
        for name in list_templates():
            assert name.startswith("card") and name.endswith(".html")


# ── Testes: _render_html internamente ────────────────────────────────────────

class TestRenderHtmlInternal:
    def test_prioridade_critica_usa_cor_vermelha(self):
        art = {**ARTICLE_MINIMAL, "priority": "critica"}
        template = "<div style='background:{{prioridade_cor}}'>{{prioridade}}</div>"
        html = _render_html(art, template)
        assert "#dc2626" in html
        assert "CRITICA" in html

