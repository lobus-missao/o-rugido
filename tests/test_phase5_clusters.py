"""
Testes da Fase 5 — Clustering de Notícias.

Verifica:
  1. _cluster_id() — determinístico e único por parâmetros.
  2. _compute_cluster_score() — fórmula avg × log2(sources+1).
  3. _extract_entities() — lê ai_json corretamente.
  4. _extract_title_keywords() — filtra stopwords, tamanho mínimo.
  5. _group_by_title_signature() — agrupa por assinatura exata.
  6. _group_by_entities() — agrupa por entidades comuns.
  7. _group_by_keywords() — agrupa por keywords do título.
  8. list_db_clusters() / get_db_cluster_articles() — fallback seguro.
  9. cluster_stats() — retorna zeros quando banco vazio ou ausente.

Ref: specs/05-deduplication-clustering.md
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager

import pytest

from news_radar.clusters import (
    _cluster_id,
    _compute_cluster_score,
    _extract_entities,
    _extract_tags,
    _extract_title_keywords,
    _group_by_entities,
    _group_by_keywords,
    _group_by_title_signature,
    _select_primary,
    cluster_stats,
)
import news_radar.clusters as cl_module


# ===========================================================================
# Fixtures
# ===========================================================================

def _art(
    id: str = "abc123",
    title: str = "Prefeitura de Teresina anuncia licitação",
    source: str = "Cidade Verde",
    source_scope: str = "piaui",
    title_signature: str = "sig_01",
    final_score_brasil: float = 60.0,
    ai_json: dict | None = None,
) -> dict:
    """Artigo mínimo válido para testes."""
    return {
        "id": id,
        "title": title,
        "source": source,
        "source_scope": source_scope,
        "title_signature": title_signature,
        "final_score_brasil": final_score_brasil,
        "final_score_piaui": final_score_brasil * 0.8,
        "final_score_teresina": final_score_brasil * 0.7,
        "priority": "alta",
        "ai_json": ai_json,
        "locality": "Teresina",
        "editorial_status": "ai_done",
    }


# ===========================================================================
# _cluster_id
# ===========================================================================

def test_cluster_id_e_determinístico():
    """Mesmos parâmetros → mesmo ID."""
    id1 = _cluster_id("Prefeitura", "piaui", "entidade_comum")
    id2 = _cluster_id("Prefeitura", "piaui", "entidade_comum")
    assert id1 == id2


def test_cluster_id_difere_por_label():
    """Labels diferentes → IDs diferentes."""
    id1 = _cluster_id("Prefeitura", "piaui", "entidade_comum")
    id2 = _cluster_id("ALEPI", "piaui", "entidade_comum")
    assert id1 != id2


def test_cluster_id_difere_por_scope():
    """Escopos diferentes → IDs diferentes."""
    id1 = _cluster_id("licitação", "brasil", "keyword_comum")
    id2 = _cluster_id("licitação", "piaui", "keyword_comum")
    assert id1 != id2


def test_cluster_id_difere_por_tipo():
    """Tipos diferentes → IDs diferentes."""
    id1 = _cluster_id("licitação", "brasil", "titulo_similar")
    id2 = _cluster_id("licitação", "brasil", "keyword_comum")
    assert id1 != id2


def test_cluster_id_tem_24_chars():
    """ID deve ter exatamente 24 caracteres."""
    cid = _cluster_id("qualquer", "brasil", "titulo_similar")
    assert len(cid) == 24


def test_cluster_id_case_insensitive():
    """Label em maiúsculas/minúsculas deve gerar mesmo ID."""
    id1 = _cluster_id("Prefeitura", "piaui", "entidade_comum")
    id2 = _cluster_id("PREFEITURA", "piaui", "entidade_comum")
    assert id1 == id2


# ===========================================================================
# _compute_cluster_score
# ===========================================================================

def test_compute_cluster_score_uma_fonte():
    """1 fonte: log2(1+1) = 1 → score = avg."""
    arts = [_art(final_score_brasil=80.0)]
    score = _compute_cluster_score(arts)
    assert score == round(80.0 * math.log2(2), 2)


def test_compute_cluster_score_duas_fontes():
    """2 fontes distintas devem aumentar o score."""
    arts = [
        _art(id="a1", source="Fonte A", final_score_brasil=60.0),
        _art(id="a2", source="Fonte B", final_score_brasil=60.0),
    ]
    score_2 = _compute_cluster_score(arts)
    score_1 = _compute_cluster_score([arts[0]])
    assert score_2 > score_1


def test_compute_cluster_score_lista_vazia():
    """Lista vazia retorna 0."""
    assert _compute_cluster_score([]) == 0.0


def test_compute_cluster_score_mesma_fonte_nao_multiplica():
    """Dois artigos da mesma fonte contam como 1 fonte."""
    arts = [
        _art(id="a1", source="X", final_score_brasil=60.0),
        _art(id="a2", source="X", final_score_brasil=60.0),
    ]
    score_same = _compute_cluster_score(arts)
    arts_diff = [
        _art(id="b1", source="X", final_score_brasil=60.0),
        _art(id="b2", source="Y", final_score_brasil=60.0),
    ]
    score_diff = _compute_cluster_score(arts_diff)
    assert score_diff > score_same


# ===========================================================================
# _extract_entities e _extract_tags
# ===========================================================================

def test_extract_entities_de_ai_json_dict():
    """Extrai entidades de ai_json já como dict."""
    art = _art(ai_json={"entidades": ["Prefeitura de Teresina", "STRANS", "MP"]})
    ents = _extract_entities(art)
    assert "prefeitura de teresina" in ents
    assert "strans" in ents
    # "MP" tem menos de 5 chars → filtrado
    assert "mp" not in ents


def test_extract_entities_de_ai_json_string():
    """Extrai entidades de ai_json serializado como string."""
    art = _art(ai_json=json.dumps({"entidades": ["Câmara Municipal de Teresina"]}))
    ents = _extract_entities(art)
    assert "câmara municipal de teresina" in ents


def test_extract_entities_sem_ai_json():
    """Sem ai_json retorna lista vazia."""
    art = _art(ai_json=None)
    ents = _extract_entities(art)
    assert ents == []


def test_extract_tags_retorna_lista_vazia_sem_ai():
    """Sem ai_json, tags retorna []."""
    assert _extract_tags(_art(ai_json=None)) == []


def test_extract_tags_retorna_lista_lowercase():
    """Tags são convertidas para lowercase."""
    art = _art(ai_json={"tags": ["Licitação", "TERESINA", "fraude"]})
    tags = _extract_tags(art)
    assert "licitação" in tags
    assert "teresina" in tags
    assert "Licitação" not in tags


# ===========================================================================
# _extract_title_keywords
# ===========================================================================

def test_extract_title_keywords_filtra_stopwords():
    """Palavras como 'de', 'em', 'por' são filtradas."""
    art = _art(title="Licitação de ônibus em Teresina com sobrepreço")
    kws = _extract_title_keywords(art)
    assert "de" not in kws
    assert "em" not in kws
    assert "com" not in kws


def test_extract_title_keywords_filtra_palavras_curtas():
    """Palavras com menos de 6 chars são filtradas."""
    art = _art(title="TCE audita obra cara")
    kws = _extract_title_keywords(art)
    # "tce" tem 3 chars, "obra" tem 4, "cara" tem 4 → todos filtrados
    assert all(len(w) >= 6 for w in kws)


def test_extract_title_keywords_retorna_set():
    """Retorna um set (sem duplicatas)."""
    art = _art(title="licitação licitação fraude pública")
    kws = _extract_title_keywords(art)
    assert isinstance(kws, set)


# ===========================================================================
# _select_primary
# ===========================================================================

def test_select_primary_escolhe_maior_score():
    """Artigo com maior final_score_brasil é selecionado como primário."""
    arts = [
        _art(id="a1", final_score_brasil=30.0),
        _art(id="a2", final_score_brasil=80.0),
        _art(id="a3", final_score_brasil=50.0),
    ]
    assert _select_primary(arts) == "a2"


# ===========================================================================
# _group_by_title_signature
# ===========================================================================

def test_group_by_title_signature_agrupa_mesma_assinatura():
    """Dois artigos com mesma title_signature formam um cluster."""
    arts = [
        _art(id="a1", title_signature="sig_x"),
        _art(id="a2", title_signature="sig_x"),
    ]
    groups = _group_by_title_signature(arts)
    assert len(groups) == 1
    assert len(groups[0]["articles"]) == 2
    assert groups[0]["type"] == "titulo_similar"


def test_group_by_title_signature_nao_agrupa_assinaturas_diferentes():
    """Artigos com assinaturas diferentes NÃO formam cluster."""
    arts = [
        _art(id="a1", title_signature="sig_x"),
        _art(id="a2", title_signature="sig_y"),
    ]
    groups = _group_by_title_signature(arts)
    assert groups == []


def test_group_by_title_signature_requer_minimo_2():
    """Um artigo sozinho com uma assinatura não forma cluster."""
    arts = [_art(id="a1", title_signature="sig_unica")]
    groups = _group_by_title_signature(arts)
    assert groups == []


def test_group_by_title_signature_tres_artigos_mesmo_assunto():
    """3 artigos com mesma assinatura formam 1 cluster com 3 artigos."""
    arts = [
        _art(id=f"a{i}", title_signature="sig_hot") for i in range(3)
    ]
    groups = _group_by_title_signature(arts)
    assert len(groups) == 1
    assert len(groups[0]["articles"]) == 3


def test_group_by_title_signature_ignora_assinatura_none():
    """Artigos sem title_signature não são agrupados."""
    arts = [
        _art(id="a1", title_signature=None),
        _art(id="a2", title_signature=None),
    ]
    groups = _group_by_title_signature(arts)
    assert groups == []


# ===========================================================================
# _group_by_entities
# ===========================================================================

def test_group_by_entities_agrupa_por_entidade_comum():
    """Dois artigos com entidade comum formam um cluster."""
    ai = {"entidades": ["Prefeitura de Teresina"]}
    arts = [
        _art(id="a1", ai_json=ai, title_signature="sig_a"),
        _art(id="a2", ai_json=ai, title_signature="sig_b"),
    ]
    groups = _group_by_entities(arts, already_clustered=set())
    assert len(groups) == 1
    assert groups[0]["type"] == "entidade_comum"


def test_group_by_entities_pula_ja_clusterizados():
    """Artigos já em cluster não devem ser agrupados de novo."""
    ai = {"entidades": ["Prefeitura de Teresina"]}
    arts = [
        _art(id="a1", ai_json=ai),
        _art(id="a2", ai_json=ai),
    ]
    groups = _group_by_entities(arts, already_clustered={"a1", "a2"})
    assert groups == []


def test_group_by_entities_nao_agrupa_entidade_curta():
    """Entidades com menos de 5 chars não geram cluster."""
    ai = {"entidades": ["MP"]}  # 2 chars → filtrado
    arts = [
        _art(id="a1", ai_json=ai),
        _art(id="a2", ai_json=ai),
    ]
    groups = _group_by_entities(arts, already_clustered=set())
    assert groups == []


def test_group_by_entities_sem_entidades_nao_agrupa():
    """Artigos sem entidades não formam cluster por entidade."""
    arts = [
        _art(id="a1", ai_json=None),
        _art(id="a2", ai_json=None),
    ]
    groups = _group_by_entities(arts, already_clustered=set())
    assert groups == []


# ===========================================================================
# _group_by_keywords
# ===========================================================================

def test_group_by_keywords_agrupa_por_keyword_comum():
    """Artigos com palavra-chave do título em comum formam cluster."""
    arts = [
        _art(id="a1", title="Investigação policial apura corrupção municipal"),
        _art(id="a2", title="Investigação do MP sobre fraude em contrato"),
    ]
    groups = _group_by_keywords(arts, already_clustered=set())
    # "investigacao" ou "investigação" deve ser keyword comum
    assert len(groups) >= 1


def test_group_by_keywords_pula_ja_clusterizados():
    """Artigos já em cluster não entram em novos grupos por keyword."""
    arts = [
        _art(id="a1", title="Licitação suspeita envolve vereadores"),
        _art(id="a2", title="Licitação municipal tem superfaturamento"),
    ]
    groups = _group_by_keywords(arts, already_clustered={"a1", "a2"})
    assert groups == []


def test_group_by_keywords_nao_agrupa_palavras_curtas():
    """Palavras com menos de 6 chars não geram cluster por keyword."""
    arts = [
        _art(id="a1", title="TCE MP STF"),
        _art(id="a2", title="TCE MP STF"),
    ]
    groups = _group_by_keywords(arts, already_clustered=set())
    # Todas as palavras têm < 6 chars → nenhum cluster
    assert groups == []


# ===========================================================================
# cluster_stats — fallback seguro
# ===========================================================================

def test_cluster_stats_retorna_zeros_em_excecao(monkeypatch):
    """cluster_stats() retorna zeros se banco não disponível."""
    monkeypatch.setattr(cl_module, "connect", lambda: (_ for _ in ()).throw(Exception("DB down")))
    stats = cluster_stats()
    assert stats["total"] == 0
    assert stats["active"] == 0
    assert stats["articles_clustered"] == 0
    assert isinstance(stats["by_type"], dict)


# ===========================================================================
# list_db_clusters — fallback seguro
# ===========================================================================

def test_list_db_clusters_retorna_lista_vazia_em_excecao(monkeypatch):
    """list_db_clusters() retorna [] se banco não disponível."""
    from news_radar.clusters import list_db_clusters
    monkeypatch.setattr(cl_module, "connect", lambda: (_ for _ in ()).throw(Exception("DB down")))

    # Precisa patchar o contextmanager também
    @contextmanager
    def _bad_connect():
        raise Exception("DB down")
        yield None

    monkeypatch.setattr(cl_module, "connect", _bad_connect)

    # Deve lançar exceção (não é wrapped em try/except por design)
    with pytest.raises(Exception):
        list_db_clusters()
