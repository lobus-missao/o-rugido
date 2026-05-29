from __future__ import annotations

import json
from contextlib import contextmanager

from news_radar import ai_batches
from news_radar.ranker import automatic_scores, TERESINA_TERMS, PIAUI_TERMS
from news_radar.text_utils import count_terms


# ── Testes de falsos positivos nos termos geográficos ─────────────────────────

def test_zona_norte_nao_e_termo_de_teresina():
    """'zona norte' é genérico demais — não deve estar em TERESINA_TERMS."""
    assert "zona norte" not in TERESINA_TERMS


def test_zona_sul_nao_e_termo_de_teresina():
    assert "zona sul" not in TERESINA_TERMS


def test_zona_leste_nao_e_termo_de_teresina():
    assert "zona leste" not in TERESINA_TERMS


def test_zona_sudeste_nao_e_termo_de_teresina():
    assert "zona sudeste" not in TERESINA_TERMS


def test_fms_nao_e_termo_de_teresina():
    """'fms' é abreviação genérica — não deve estar em TERESINA_TERMS."""
    assert "fms" not in TERESINA_TERMS


def test_picos_nao_e_termo_do_piaui():
    """'picos' causa falso positivo em 'picos de calor' — não deve estar em PIAUI_TERMS."""
    assert "picos" not in PIAUI_TERMS


def test_artigo_sao_paulo_zona_norte_nao_pontua_teresina():
    """Artigo sobre São Paulo mencionando 'zona norte' não deve pontuar para Teresina."""
    scores = automatic_scores({
        "title": "Obras na zona norte de São Paulo avançam",
        "summary": "A prefeitura de São Paulo anunciou obras na zona norte da cidade.",
        "source_scope": "brasil",
        "source_trust": 0.7,
    })
    assert scores["auto_score_teresina"] == 0 or scores["auto_score_teresina"] < scores["auto_score_brasil"]


def test_artigo_picos_calor_nao_pontua_piaui():
    """Artigo sobre 'picos de calor' não deve pontuar para Piauí por conta do termo 'picos'."""
    scores = automatic_scores({
        "title": "Picos de calor batem recordes no Brasil",
        "summary": "As temperaturas atingiram picos históricos em várias cidades brasileiras.",
        "source_scope": "brasil",
        "source_trust": 0.7,
    })
    # Sem "piaui", "piauí" ou termos específicos, score_piaui deve ser baixo
    # O teste verifica que não há contribuição espúria do falso positivo 'picos'
    from news_radar.text_utils import count_terms
    text = "picos de calor batem recordes no brasil as temperaturas atingiram picos historicos em varias cidades brasileiras"
    piaui_count = count_terms(text, PIAUI_TERMS)
    assert piaui_count == 0, f"'picos' causaria falso positivo — count={piaui_count}"


def test_artigo_teresina_pontua_corretamente():
    """Artigo genuinamente sobre Teresina deve continuar pontuando alto."""
    scores = automatic_scores({
        "title": "SEMEC de Teresina anuncia novas vagas em escolas municipais",
        "summary": "A secretaria municipal de educação teresinense abriu inscrições.",
        "source_scope": "teresina",
        "source_trust": 0.8,
        "published_at": "2026-05-28T10:00:00+00:00",
    })
    assert scores["auto_score_teresina"] > 0


def test_ranker_scores_public_interest_news():
    scores = automatic_scores({
        "title": "TCE-PI investiga contrato milionário da Prefeitura de Teresina",
        "summary": "Denúncia aponta irregularidade em licitação de saúde pública.",
        "source_scope": "teresina",
        "source_trust": 0.8,
        "published_at": "2026-05-28T10:00:00+00:00",
    })

    assert scores["auto_score_teresina"] > scores["auto_score_brasil"]
    assert scores["final_score_teresina"] > 0
    assert scores["reasons"]


def test_make_ai_batches_without_database(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_batches, "AI_BATCHES_DIR", tmp_path)
    monkeypatch.setattr(ai_batches, "_save_batch_record", lambda **kwargs: None)
    monkeypatch.setattr(
        ai_batches,
        "top_articles",
        lambda **kwargs: [{
            "id": "art-1",
            "title": "Notícia relevante",
            "source": "Fonte",
            "published_at": "2026-05-28T10:00:00+00:00",
            "summary": "Resumo curto de teste",
            "canonical_url": "https://example.com/a",
        }],
    )

    generated = ai_batches.make_ai_batches(scope="brasil", top=1, batch_size=1)

    assert len(generated) == 1
    assert generated[0]["items"] == 1
    assert (tmp_path / f"{generated[0]['batch_id']}.json").exists()
    assert (tmp_path / f"{generated[0]['batch_id']}.prompt.txt").exists()


class FakeCursor:
    def __init__(self):
        self.row = None
        self.updated = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if query.strip().startswith("SELECT id"):
            self.row = {
                "id": params[0],
                "auto_score_brasil": 50,
                "auto_score_piaui": 60,
                "auto_score_teresina": 70,
            }
        elif query.strip().startswith("UPDATE articles"):
            self.updated += 1

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


@contextmanager
def fake_connect():
    yield FakeConn()


def test_import_ai_result_updates_matching_article(monkeypatch, tmp_path):
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps([{
        "id": "art-1",
        "interesse_publico": 8,
        "impacto_social": 7,
        "urgencia": 6,
        "relevancia_local": 9,
        "dinheiro_publico": 8,
        "prioridade": "alta",
        "editoria": "Poder",
        "entidades": ["TCE-PI"],
    }]), encoding="utf-8")
    monkeypatch.setattr(ai_batches, "connect", fake_connect)

    imported = ai_batches.import_ai_result(result_file)

    assert imported["updated"] == 1
    assert imported["ignored"] == 0
