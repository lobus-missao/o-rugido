"""Fase 7 — Testes de geração de card editorial via HTML/PNG.

Cobre: build_card_context, render_card_html, save_card_html, list_templates,
validação de dados obrigatórios, fallback sem ai_json, overrides, e ausência
de placeholders crus no HTML final.
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

from news_radar.card_renderer import (
    _render_html,
    build_card_context,
    list_templates,
    render_card_html,
    save_card_html,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

ARTICLE_FULL = {
    "id": "abc123def456789012",
    "title": "Prefeitura anuncia pacote de obras",
    "url": "https://exemplo.com/obras",
    "canonical_url": "https://exemplo.com/obras",
    "source": "Cidade Verde",
    "source_scope": "teresina",
    "source_trust": 0.74,
    "published_at": "2026-05-29T10:00:00+00:00",
    "summary": "A Prefeitura de Teresina abriu licitação para obras de recapeamento. " * 5,
    "priority": "alta",
    "category": "Governos e politica",
    "ai_score": 7.8,
    "final_score_brasil": 62.0,
    "final_score_piaui": 71.0,
    "final_score_teresina": 85.0,
    "locality": "Teresina",
    "ai_json": {
        "titulo_sugerido": "Teresina abre licitação para recapeamento de ruas",
        "subtitulo_sugerido": "Investimento previsto de R$ 12 milhões",
        "resumo_curto": "Prefeitura lança licitação de R$ 12 mi para obras nas zonas Norte e Sul.",
        "pontos_chave": [
            "R$ 12 milhões em obras",
            "Zonas Norte e Sul beneficiadas",
            "Prazo de 180 dias",
        ],
        "localidade": "Teresina",
        "entidades": ["Prefeitura de Teresina", "SEMDUH"],
        "tags": ["obras", "licitação", "infraestrutura"],
        "justificativa_score": "Alto impacto local — investimento em infraestrutura pública.",
        "editoria": "Governos e politica",
    },
}

ARTICLE_MINIMAL = {
    "id": "min001min002min003",
    "title": "Evento ocorre amanhã em Teresina",
    "source": "Portal PI",
    "source_scope": "piaui",
    "final_score_piaui": 40.0,
}

ARTICLE_NO_AI = {
    "id": "noai0001noai0002no",
    "title": "Artigo sem dados de IA",
    "source": "G1 PI",
    "source_scope": "brasil",
    "summary": "Um resumo simples mas com mais de cinquenta caracteres para testar o conteudo_tag.",
    "priority": "media",
    "category": "Geral",
    "final_score_brasil": 45.0,
    "published_at": "2026-05-28",
}

RAW_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}")


# ── Testes: build_card_context ────────────────────────────────────────────────

class TestBuildCardContext:
    def test_titulo_usa_titulo_sugerido_da_ia(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["titulo"] == "Teresina abre licitação para recapeamento de ruas"

    def test_titulo_fallback_para_title_sem_ai(self):
        ctx = build_card_context(ARTICLE_MINIMAL)
        assert ctx["titulo"] == ARTICLE_MINIMAL["title"]

    def test_title_override_tem_prioridade(self):
        ctx = build_card_context(ARTICLE_FULL, title_override="Título Manual")
        assert ctx["titulo"] == "Título Manual"

    def test_subtitle_override_tem_prioridade(self):
        ctx = build_card_context(ARTICLE_FULL, subtitle_override="Sub manual")
        assert "Sub manual" in ctx["subtitulo_html"]

    def test_subtitulo_html_vazio_sem_dado(self):
        ctx = build_card_context(ARTICLE_NO_AI)
        assert ctx["subtitulo_html"] == ""

    def test_subtitulo_html_preenchido_com_ai_json(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert "Investimento previsto" in ctx["subtitulo_html"]

    def test_score_usa_escopo_correto(self):
        ctx_br = build_card_context(ARTICLE_FULL, scope="brasil")
        ctx_te = build_card_context(ARTICLE_FULL, scope="teresina")
        assert ctx_br["score"] == "62"
        assert ctx_te["score"] == "85"

    def test_score_fallback_sem_escopo(self):
        ctx = build_card_context(ARTICLE_FULL)
        # Deve pegar o primeiro não-zero entre brasil/piaui/teresina
        assert ctx["score"] in ("62", "71", "85")

    def test_prioridade_label_alta(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["prioridade"] == "ALTA"

    def test_prioridade_label_media(self):
        ctx = build_card_context(ARTICLE_NO_AI)
        assert ctx["prioridade"] == "MEDIA"

    def test_prioridade_cor_alta(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["prioridade_cor"] == "#ea580c"

    def test_prioridade_cor_desconhecida_usa_default(self):
        art = {**ARTICLE_MINIMAL, "priority": "desconhecida"}
        ctx = build_card_context(art)
        assert ctx["prioridade_cor"] == "#6b7280"

    def test_ia_badge_com_ai_score(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert ctx["ia_badge"] == "IA"

    def test_ia_badge_sem_ai_score(self):
        ctx = build_card_context(ARTICLE_MINIMAL)
        assert ctx["ia_badge"] == "AUTO"

    def test_pontos_chave_maximo_4(self):
        art = {
            **ARTICLE_NO_AI,
            "ai_json": {"pontos_chave": ["p1", "p2", "p3", "p4", "p5", "p6"]},
        }
        ctx = build_card_context(art)
        assert ctx["pontos_chave"].count("<li>") == 4

    def test_entidades_maximo_3(self):
        art = {
            **ARTICLE_NO_AI,
            "ai_json": {"entidades": ["E1", "E2", "E3", "E4", "E5"]},
        }
        ctx = build_card_context(art)
        assert ctx["entidades_tags"].count("entidade") == 3

    def test_categoria_tag_gerada_com_categoria(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert "tag-categoria" in ctx["categoria_tag"]
        assert "Governos" in ctx["categoria_tag"]

    def test_categoria_tag_vazia_para_hifen(self):
        art = {**ARTICLE_MINIMAL, "category": "-"}
        ctx = build_card_context(art)
        assert ctx["categoria_tag"] == ""

    def test_pontos_html_block_para_base_template(self):
        ctx = build_card_context(ARTICLE_FULL)
        assert "card-pontos" in ctx["pontos_html"]
        assert "<ul>" in ctx["pontos_html"]

    def test_pontos_html_vazio_sem_pontos(self):
        ctx = build_card_context(ARTICLE_NO_AI)
        assert ctx["pontos_html"] == ""

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
        assert not RAW_PLACEHOLDER_PATTERN.search(html), (
            "HTML final contém placeholder cru em card.html"
        )

    def test_renderiza_sem_placeholders_crus_base_html(self):
        base = TEMPLATES_DIR / "card-editorial-base.html"
        if not base.exists():
            pytest.skip("card-editorial-base.html não encontrado")
        html = render_card_html(ARTICLE_FULL, template_name="card-editorial-base.html")
        assert not RAW_PLACEHOLDER_PATTERN.search(html), (
            "HTML final contém placeholder cru em card-editorial-base.html"
        )

    def test_titulo_aparece_no_html(self):
        html = render_card_html(ARTICLE_FULL)
        assert "Teresina abre licitação" in html

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
        art = {**ARTICLE_FULL, "title": "", "ai_json": {}}
        with pytest.raises(ValueError, match="titulo"):
            render_card_html(art)

    def test_raise_sem_source(self):
        art = {**ARTICLE_FULL, "source": ""}
        with pytest.raises(ValueError, match="fonte"):
            render_card_html(art)

    def test_raise_template_inexistente(self):
        with pytest.raises(FileNotFoundError):
            render_card_html(ARTICLE_FULL, template_name="nao_existe.html")

    def test_fallback_sem_ai_json_sem_placeholders_crus(self):
        html = render_card_html(ARTICLE_NO_AI)
        assert not RAW_PLACEHOLDER_PATTERN.search(html)

    def test_artigo_minimal_sem_placeholders_crus(self):
        html = render_card_html(ARTICLE_MINIMAL)
        assert not RAW_PLACEHOLDER_PATTERN.search(html)

    def test_subtitulo_html_em_base_template(self):
        base = TEMPLATES_DIR / "card-editorial-base.html"
        if not base.exists():
            pytest.skip("card-editorial-base.html não encontrado")
        html = render_card_html(ARTICLE_FULL, template_name="card-editorial-base.html")
        assert "Investimento previsto de R$ 12 milhões" in html

    def test_card_html_contem_div_card(self):
        html = render_card_html(ARTICLE_FULL)
        assert 'id="card"' in html


# ── Testes: save_card_html ────────────────────────────────────────────────────

class TestSaveCardHtml:
    def test_salva_arquivo_html(self, tmp_path, monkeypatch):
        import news_radar.card_renderer as cr

        monkeypatch.setattr(cr, "CARDS_DIR", tmp_path)

        html_content = "<html><body>Test card</body></html>"
        art_id = "testid12345678901234"
        path = save_card_html(art_id, html_content)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == html_content

    def test_nome_do_arquivo_usa_16_chars_do_id(self, tmp_path, monkeypatch):
        import news_radar.card_renderer as cr

        monkeypatch.setattr(cr, "CARDS_DIR", tmp_path)
        art_id = "abcdef1234567890xyz"
        path = save_card_html(art_id, "<html/>")
        assert path.name == f"card_{art_id[:16]}.html"

    def test_sobrescreve_arquivo_existente(self, tmp_path, monkeypatch):
        import news_radar.card_renderer as cr

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

    def test_score_inteiro_sem_decimais(self):
        art = {**ARTICLE_FULL}
        template = "score={{score}}"
        html = _render_html(art, template, scope="brasil")
        assert html == "score=62"

    def test_resumo_truncado_a_200_chars(self):
        art = {**ARTICLE_NO_AI, "summary": "X" * 300}
        template = "{{resumo}}"
        html = _render_html(art, template)
        assert len(html) <= 200

    def test_ai_json_como_string_json_e_parseado(self):
        art = {
            **ARTICLE_MINIMAL,
            "ai_json": '{"titulo_sugerido": "Titulo via string JSON"}',
        }
        ctx = build_card_context(art)
        assert ctx["titulo"] == "Titulo via string JSON"

    def test_ai_json_invalido_usa_fallback(self):
        art = {**ARTICLE_MINIMAL, "ai_json": "{nao e json valido}"}
        ctx = build_card_context(art)
        assert ctx["titulo"] == ARTICLE_MINIMAL["title"]

    def test_localidade_de_locality_quando_sem_ai_json(self):
        art = {**ARTICLE_MINIMAL, "locality": "Parnaíba"}
        ctx = build_card_context(art)
        assert "Parnaíba" in ctx["localidade_tag"]
