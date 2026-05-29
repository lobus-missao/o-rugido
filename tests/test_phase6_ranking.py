"""
Testes da Fase 6 — Ranking Explicável.

Verifica:
  1. explain_cluster_score() — sinais, dimensões IA, explicação.
  2. rank_clusters_by_dimension() — ordenação por diferentes dimensões.
  3. score_summary() — extração de top dimensões IA.
  4. _extract_ai_dimension() — lê ai_json corretamente.
  5. _avg_ai_dimensions() — médias corretas.
  6. Fórmulas de score auto: não negativo, não > 100, bônus geográfico.
  7. explain_score() já integrado: campos esperados.

Ref: specs/06-ranking-engine.md, skills/testing-review-patterns.md
"""
from __future__ import annotations

import json
import math

import pytest

from news_radar.ranking import (
    RANKING_DIMENSIONS,
    DEFAULT_WEIGHTS,
    DIMENSION_ICONS,
    AI_NUMERIC_DIMENSIONS,
    _extract_ai_dimension,
    _avg_ai_dimensions,
    _parse_ai_json,
    explain_cluster_score,
    rank_clusters_by_dimension,
    score_summary,
)
from news_radar.score_explainer import explain_score
from news_radar.ranker import automatic_scores, combine_with_ai, ai_score_from_payload


# ===========================================================================
# Fixtures
# ===========================================================================

_DEFAULT_AI_JSON = object()  # sentinel para distinguir "padrão" de None explícito

def _art(
    id: str = "art1",
    title: str = "Prefeitura anuncia licitação suspeita",
    source: str = "Cidade Verde",
    source_scope: str = "piaui",
    source_trust: float = 0.75,
    final_score_brasil: float = 65.0,
    ai_score: float | None = 7.5,
    ai_json=_DEFAULT_AI_JSON,
) -> dict:
    base_ai = {
        "interesse_publico": 8,
        "impacto_social": 7,
        "gravidade": 6,
        "risco_investigativo": 9,
        "dinheiro_publico": 8,
        "relevancia_politica": 5,
        "urgencia": 7,
        "relevancia_local": 9,
        "resumo_curto": "Prefeitura licitou com indício de sobrepreço.",
        "justificativa_score": "Alto risco investigativo.",
    }
    # ai_json=_DEFAULT_AI_JSON → usa base_ai; ai_json=None → None explícito
    resolved_ai_json = base_ai if ai_json is _DEFAULT_AI_JSON else ai_json
    return {
        "id": id,
        "title": title,
        "source": source,
        "source_scope": source_scope,
        "source_trust": source_trust,
        "final_score_brasil": final_score_brasil,
        "auto_score_brasil": final_score_brasil * 0.7,
        "ai_score": ai_score,
        "ai_json": resolved_ai_json,
        "summary": "A prefeitura abriu processo licitatório com indícios de irregularidade.",
        "published_at": None,
        "editorial_status": "ai_done",
    }


def _cluster(
    id: str = "cluster1",
    title: str = "Licitação suspeita em Teresina",
    scope: str = "piaui",
    cluster_type: str = "titulo_similar",
    article_count: int = 3,
    source_count: int = 2,
    cluster_score: float = 55.0,
) -> dict:
    return {
        "id": id,
        "title": title,
        "scope": scope,
        "cluster_type": cluster_type,
        "article_count": article_count,
        "source_count": source_count,
        "cluster_score": cluster_score,
        "status": "active",
        "rank_value": cluster_score,
        "rank_dimension": "cluster_score",
    }


# ===========================================================================
# _extract_ai_dimension
# ===========================================================================

def test_extract_ai_dimension_de_dict():
    """Extrai dimensão de ai_json já como dict."""
    art = _art(ai_json={"risco_investigativo": 9, "dinheiro_publico": 7})
    assert _extract_ai_dimension(art, "risco_investigativo") == 9.0
    assert _extract_ai_dimension(art, "dinheiro_publico") == 7.0


def test_extract_ai_dimension_de_string_json():
    """Extrai dimensão de ai_json serializado como string."""
    art = _art(ai_json=json.dumps({"urgencia": 8}))
    assert _extract_ai_dimension(art, "urgencia") == 8.0


def test_extract_ai_dimension_ausente_retorna_zero():
    """Dimensão ausente retorna 0."""
    art = _art(ai_json={"risco_investigativo": 9})
    assert _extract_ai_dimension(art, "polemica") == 0.0


def test_extract_ai_dimension_sem_ai_json_retorna_zero():
    """Sem ai_json retorna 0."""
    art = _art(ai_json=None)
    assert _extract_ai_dimension(art, "gravidade") == 0.0


def test_extract_ai_dimension_valor_nao_numerico_retorna_zero():
    """Valor não numérico retorna 0."""
    art = _art(ai_json={"urgencia": "alta"})
    assert _extract_ai_dimension(art, "urgencia") == 0.0


# ===========================================================================
# _avg_ai_dimensions
# ===========================================================================

def test_avg_ai_dimensions_sem_artigos_com_ia():
    """Sem artigos com ai_score retorna dict vazio."""
    arts = [_art(ai_score=None)]
    result = _avg_ai_dimensions(arts)
    assert result == {}


def test_avg_ai_dimensions_calcula_media_correta():
    """Média de dimensão com 2 artigos."""
    arts = [
        _art(id="a1", ai_score=7.0, ai_json={"risco_investigativo": 8}),
        _art(id="a2", ai_score=8.0, ai_json={"risco_investigativo": 10}),
    ]
    result = _avg_ai_dimensions(arts)
    assert result["risco_investigativo"] == pytest.approx(9.0, abs=0.1)


def test_avg_ai_dimensions_ignora_artigos_sem_ia():
    """Artigos sem ai_score são ignorados."""
    arts = [
        _art(id="a1", ai_score=7.0, ai_json={"gravidade": 6}),
        _art(id="a2", ai_score=None, ai_json={"gravidade": 10}),  # sem IA → ignorado
    ]
    result = _avg_ai_dimensions(arts)
    assert result["gravidade"] == pytest.approx(6.0, abs=0.1)


# ===========================================================================
# explain_cluster_score
# ===========================================================================

def test_explain_cluster_score_sem_artigos():
    """Cluster sem artigos retorna explicação padrão."""
    c = _cluster()
    result = explain_cluster_score(c, [])
    assert result["total"] == c["cluster_score"]
    assert result["avg_score"] == 0.0
    assert result["has_ai"] is False
    assert "explanation" in result


def test_explain_cluster_score_com_artigos_com_ia():
    """Cluster com artigos com IA retorna dimensões preenchidas."""
    c = _cluster(source_count=3, article_count=3)
    arts = [_art(id=f"a{i}", ai_score=7.0) for i in range(3)]
    result = explain_cluster_score(c, arts)
    assert result["has_ai"] is True
    assert result["ai_article_count"] == 3
    assert len(result["ai_dimensions"]) > 0
    assert "explanation" in result
    assert len(result["explanation"]) > 0


def test_explain_cluster_score_sem_ia():
    """Cluster sem artigos IA retorna ai_dimensions vazio."""
    c = _cluster()
    arts = [_art(id=f"a{i}", ai_score=None, ai_json=None) for i in range(2)]
    result = explain_cluster_score(c, arts)
    assert result["has_ai"] is False
    assert result["ai_dimensions"] == {}


def test_explain_cluster_score_sinaliza_fontes():
    """Com 4+ fontes, sinal de múltiplas fontes aparece."""
    c = _cluster(source_count=4)
    arts = [_art(id=f"a{i}", source=f"fonte_{i}", ai_score=None, ai_json=None) for i in range(4)]
    result = explain_cluster_score(c, arts)
    assert any("fontes" in s for s in result["signals"])


def test_explain_cluster_score_sinaliza_risco_alto():
    """risco_investigativo >= 7 gera sinal de risco."""
    c = _cluster()
    arts = [_art(id=f"a{i}", ai_score=8.0, ai_json={"risco_investigativo": 9}) for i in range(2)]
    result = explain_cluster_score(c, arts)
    assert any("risco" in s.lower() for s in result["signals"])


def test_explain_cluster_score_top_dimension_preenchida():
    """top_dimension aponta para dimensão mais relevante."""
    c = _cluster()
    arts = [_art(
        id=f"a{i}", ai_score=8.0,
        ai_json={"risco_investigativo": 9, "dinheiro_publico": 5, "gravidade": 4}
    ) for i in range(2)]
    result = explain_cluster_score(c, arts)
    assert result["top_dimension"] is not None


# ===========================================================================
# rank_clusters_by_dimension
# ===========================================================================

def test_rank_by_cluster_score_ordena_decrescente():
    """rank_clusters_by_dimension com cluster_score ordena do maior para o menor."""
    clusters = [
        _cluster(id="c1", cluster_score=30.0),
        _cluster(id="c2", cluster_score=80.0),
        _cluster(id="c3", cluster_score=50.0),
    ]
    result = rank_clusters_by_dimension(clusters, {}, "cluster_score")
    scores = [c["rank_value"] for c in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0]["id"] == "c2"


def test_rank_by_source_count():
    """Ranking por source_count ordena corretamente."""
    clusters = [
        _cluster(id="c1", source_count=1, cluster_score=90),
        _cluster(id="c2", source_count=5, cluster_score=30),
    ]
    result = rank_clusters_by_dimension(clusters, {}, "source_count")
    assert result[0]["id"] == "c2"
    assert result[0]["rank_value"] == 5


def test_rank_by_ai_dimension():
    """Ranking por dimensão IA usa média dos artigos."""
    art_c1 = _art(id="a1", ai_score=8.0, ai_json={"risco_investigativo": 9})
    art_c2 = _art(id="a2", ai_score=5.0, ai_json={"risco_investigativo": 3})
    clusters = [
        _cluster(id="c1", cluster_score=40),
        _cluster(id="c2", cluster_score=60),
    ]
    articles_by_cluster = {"c1": [art_c1], "c2": [art_c2]}
    result = rank_clusters_by_dimension(clusters, articles_by_cluster, "risco_investigativo")
    assert result[0]["id"] == "c1"
    assert result[0]["rank_value"] == pytest.approx(9.0, abs=0.1)


def test_rank_por_ai_dimension_sem_ia_retorna_zero():
    """Cluster sem artigos IA tem rank_value=0 para dimensão IA."""
    art = _art(id="a1", ai_score=None, ai_json=None)
    clusters = [_cluster(id="c1", cluster_score=50)]
    result = rank_clusters_by_dimension(clusters, {"c1": [art]}, "risco_investigativo")
    assert result[0]["rank_value"] == 0.0


def test_rank_adiciona_rank_dimension():
    """rank_clusters_by_dimension adiciona campo rank_dimension a cada cluster."""
    clusters = [_cluster()]
    result = rank_clusters_by_dimension(clusters, {}, "dinheiro_publico")
    assert result[0]["rank_dimension"] == "dinheiro_publico"


def test_rank_lista_vazia():
    """rank_clusters_by_dimension com lista vazia retorna lista vazia."""
    result = rank_clusters_by_dimension([], {}, "cluster_score")
    assert result == []


# ===========================================================================
# score_summary
# ===========================================================================

def test_score_summary_com_ia():
    """score_summary retorna score final, auto, IA e top dimensões."""
    art = _art(ai_score=7.5)
    summ = score_summary(art, "brasil")
    assert summ["has_ai"] is True
    assert summ["ai"] == pytest.approx(7.5, abs=0.1)
    assert summ["final"] > 0
    assert isinstance(summ["top_dimensions"], list)
    assert len(summ["top_dimensions"]) <= 3


def test_score_summary_sem_ia():
    """score_summary sem IA retorna ai=None e top_dimensions vazio."""
    art = _art(ai_score=None, ai_json=None)
    summ = score_summary(art, "brasil")
    assert summ["has_ai"] is False
    assert summ["ai"] is None
    assert summ["top_dimensions"] == []


def test_score_summary_top_dimensions_ordenadas_por_valor():
    """Top dimensões devem estar em ordem decrescente de valor."""
    art = _art(ai_score=8.0, ai_json={
        "risco_investigativo": 9,
        "dinheiro_publico": 7,
        "gravidade": 5,
    })
    summ = score_summary(art, "brasil")
    vals = [v for _, v in summ["top_dimensions"]]
    assert vals == sorted(vals, reverse=True)


# ===========================================================================
# explain_score (score_explainer — já existente, testar integração)
# ===========================================================================

def test_explain_score_nao_negativo():
    """Score total nunca é negativo."""
    art = {"title": "", "summary": "", "source_scope": "brasil",
           "source_trust": 0.5, "published_at": None}
    result = explain_score(art, "brasil")
    assert result["total"] >= 0


def test_explain_score_nao_passa_100():
    """Score total nunca passa de 100."""
    art = {
        "title": "TCU CGU STF PF investigação corrupção licitação fraude Teresina Piauí prefeitura vereador",
        "summary": "Operação federal apura desvio de dinheiro público em licitação municipal superfaturada",
        "source_scope": "teresina",
        "source_trust": 1.0,
        "published_at": None,
    }
    for scope in ["brasil", "piaui", "teresina"]:
        result = explain_score(art, scope)
        assert result["total"] <= 100, f"Score {scope}={result['total']} > 100"


def test_explain_score_artigo_local_maior_que_nacional_em_teresina():
    """Artigo de Teresina deve ter score > artigo nacional no escopo Teresina."""
    local = {
        "title": "Prefeitura de Teresina abre edital de licitação",
        "summary": "A Prefeitura de Teresina publicou edital para obras na zona norte.",
        "source_scope": "teresina",
        "source_trust": 0.74,
        "published_at": None,
    }
    nacional = {
        "title": "Governo Federal anuncia programa econômico",
        "summary": "O governo federal anunciou medidas para o setor industrial.",
        "source_scope": "brasil",
        "source_trust": 0.8,
        "published_at": None,
    }
    score_local = explain_score(local, "teresina")["total"]
    score_nacional = explain_score(nacional, "teresina")["total"]
    assert score_local > score_nacional


def test_explain_score_retorna_componentes():
    """explain_score retorna dict com todos os campos esperados."""
    art = _art()
    result = explain_score(art, "brasil")
    assert "total" in result
    assert "components" in result
    assert "explanation" in result
    assert "signals" in result
    assert "money_values_found" in result


# ===========================================================================
# automatic_scores e combine_with_ai (ranker — testar fórmula)
# ===========================================================================

def test_auto_score_nao_negativo():
    """auto_score nunca é negativo."""
    art = {"title": "", "summary": "", "source_scope": "brasil", "source_trust": 0.0}
    scores = automatic_scores(art)
    for col in ["auto_score_brasil", "auto_score_piaui", "auto_score_teresina"]:
        assert scores[col] >= 0, f"{col} = {scores[col]} é negativo"


def test_auto_score_nao_passa_100():
    """auto_score nunca passa de 100."""
    art = {
        "title": "TCU CGU STF PF investigação corrupção licitação Teresina prefeitura",
        "summary": "Fraude, desvio, dinheiro público, hospital, escola, transporte." * 5,
        "source_scope": "teresina",
        "source_trust": 1.0,
        "published_at": None,
    }
    scores = automatic_scores(art)
    for col in ["auto_score_brasil", "auto_score_piaui", "auto_score_teresina"]:
        assert scores[col] <= 100, f"{col} = {scores[col]} > 100"


def test_combine_with_ai_formula():
    """final_score = auto × 0.58 + ai × 0.42."""
    result = combine_with_ai(60.0, 80.0)
    expected = round(60.0 * 0.58 + 80.0 * 0.42, 2)
    assert result == expected


def test_combine_with_ai_sem_ia_retorna_auto():
    """Sem ai_score, final_score = auto_score."""
    assert combine_with_ai(60.0, None) == 60.0


# ===========================================================================
# Constantes do módulo
# ===========================================================================

def test_ranking_dimensions_tem_cluster_score():
    """RANKING_DIMENSIONS deve incluir cluster_score."""
    assert "cluster_score" in RANKING_DIMENSIONS


def test_default_weights_risco_e_dinheiro_tem_peso_maior():
    """risco_investigativo e dinheiro_publico têm peso > 1."""
    assert DEFAULT_WEIGHTS["risco_investigativo"] > 1.0
    assert DEFAULT_WEIGHTS["dinheiro_publico"] > 1.0


def test_dimension_icons_inclui_dimensoes_principais():
    """DIMENSION_ICONS inclui dimensões editorialmente relevantes."""
    for dim in ["risco_investigativo", "dinheiro_publico", "urgencia", "relevancia_local"]:
        assert dim in DIMENSION_ICONS, f"'{dim}' ausente em DIMENSION_ICONS"
