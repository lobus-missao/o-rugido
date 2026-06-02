from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from news_radar.services.ranker import (
    PIAUI_TERMS,
    PUBLIC_ORG_TERMS,
    TERESINA_TERMS,
    ai_score_from_payload,
    automatic_scores,
    clamp,
    combine_with_ai,
    parse_datetime,
    recency_score,
)


# ── clamp ────────────────────────────────────────────────────────────────────

class TestClamp:
    def test_dentro_do_intervalo(self):
        assert clamp(50) == 50

    def test_acima_do_max(self):
        assert clamp(150) == 100

    def test_abaixo_do_min(self):
        assert clamp(-10) == 0

    def test_intervalo_custom(self):
        assert clamp(50, min_value=20, max_value=40) == 40
        assert clamp(10, min_value=20, max_value=40) == 20


# ── combine_with_ai ──────────────────────────────────────────────────────────

class TestCombineWithAI:
    def test_sem_ai_retorna_auto(self):
        assert combine_with_ai(70.0, None) == 70.0

    def test_com_ai_aplica_peso(self):
        # 70 * 0.58 + 30 * 0.42 = 40.6 + 12.6 = 53.2
        result = combine_with_ai(70.0, 30.0)
        assert result == pytest.approx(53.2, abs=0.01)

    def test_clampa_no_max(self):
        assert combine_with_ai(150.0, 200.0) == 100.0

    def test_aceita_strings_numericas(self):
        # combine_with_ai aceita float(); valores em string numérica passam
        assert combine_with_ai("80", "50") == pytest.approx(67.4, abs=0.01)


# ── ai_score_from_payload ────────────────────────────────────────────────────

class TestAIScoreFromPayload:
    def test_campos_modernos(self):
        payload = {
            "interesse_publico": 8,
            "impacto_social": 7,
            "urgencia": 6,
            "relevancia_local": 9,
            "dinheiro_publico": 5,
        }
        # média = (8+7+6+9+5)/5 = 7.0 → score = 70.0
        assert ai_score_from_payload(payload) == pytest.approx(70.0, abs=0.01)

    def test_campos_legacy(self):
        # Sem nenhum campo "modern" — força fallback para legacy_fields
        payload = {
            "impacto_publico": 6,
            "gravidade": 8,
            "relevancia_politica": 5,
            "risco_investigativo": 7,
        }
        # avg de 4 campos preenchidos + 1 ausente (=0): (6+8+5+7+0)/5 = 5.2 → 52.0
        assert ai_score_from_payload(payload) == pytest.approx(52.0, abs=0.01)

    def test_payload_vazio_retorna_zero(self):
        assert ai_score_from_payload({}) == 0

    def test_valores_invalidos_viram_zero(self):
        payload = {"interesse_publico": "n/a", "impacto_social": None}
        assert ai_score_from_payload(payload) == 0


# ── recency_score ────────────────────────────────────────────────────────────

class TestRecencyScore:
    def test_sem_data_retorna_padrao(self):
        assert recency_score(None) == 3.0

    def test_recente_pontua_alto(self):
        now = datetime.now(timezone.utc).isoformat()
        score = recency_score(now)
        assert score > 8.0

    def test_antigo_pontua_baixo(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        score = recency_score(old)
        assert score < 3.0


# ── parse_datetime ───────────────────────────────────────────────────────────

class TestParseDatetime:
    def test_iso_string(self):
        result = parse_datetime("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026

    def test_string_invalida_retorna_none(self):
        assert parse_datetime("não é data") is None

    def test_none_retorna_none(self):
        assert parse_datetime(None) is None


# ── automatic_scores ─────────────────────────────────────────────────────────

class TestAutomaticScores:
    def _article(self, **overrides) -> dict:
        base = {
            "title": "Notícia genérica",
            "summary": "Conteúdo genérico sem termos específicos.",
            "source_scope": "piaui",
            "source_trust": 0.5,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        base.update(overrides)
        return base

    def test_retorna_chaves_esperadas(self):
        scores = automatic_scores(self._article())
        assert "auto_score_piaui" in scores
        assert "final_score_piaui" in scores
        assert "reasons" in scores

    def test_score_no_intervalo(self):
        scores = automatic_scores(self._article())
        assert 0 <= scores["final_score_piaui"] <= 100

    def test_termos_piaui_aumentam_score(self):
        sem_piaui = automatic_scores(self._article(
            title="Reforma fiscal aprovada", source_scope="brasil"
        ))
        com_piaui = automatic_scores(self._article(
            title="Governo do Piauí anuncia reforma fiscal",
            summary="O governador Rafael Fonteles confirmou.",
            source_scope="piaui",
        ))
        assert com_piaui["final_score_piaui"] > sem_piaui["final_score_piaui"]

    def test_termos_teresina_dao_bonus(self):
        sem_teresina = automatic_scores(self._article(
            title="Obras em Parnaíba", source_scope="piaui",
        ))
        com_teresina = automatic_scores(self._article(
            title="Prefeitura de Teresina anuncia obras",
            summary="A capital piauiense terá novos investimentos.",
            source_scope="piaui",
        ))
        assert com_teresina["final_score_piaui"] >= sem_teresina["final_score_piaui"]

    def test_sem_termos_locais_penalizado(self):
        sem_local = automatic_scores(self._article(
            title="Eleição americana",
            summary="Resultado da eleição nos EUA.",
            source_scope="brasil",
        ))
        # Sem nenhum termo Piauí/Teresina, score fica baixo (multiplicado por 0.55)
        assert sem_local["final_score_piaui"] < 40

    def test_reasons_e_lista(self):
        scores = automatic_scores(self._article(
            title="Governo do Piauí investe em saúde",
            summary="Prefeitura de Teresina libera R$ 5 milhões.",
        ))
        assert isinstance(scores["reasons"], list)


# ── listas de termos ─────────────────────────────────────────────────────────

class TestTermLists:
    def test_piaui_terms_nao_vazio(self):
        assert len(PIAUI_TERMS) > 0
        assert "piauí" in PIAUI_TERMS or "piaui" in PIAUI_TERMS

    def test_teresina_terms_nao_vazio(self):
        assert len(TERESINA_TERMS) > 0
        assert any("teresina" in t.lower() for t in TERESINA_TERMS)

    def test_public_org_terms_inclui_orgaos_basicos(self):
        text = " ".join(PUBLIC_ORG_TERMS).lower()
        assert "governo" in text
        assert "prefeitura" in text
