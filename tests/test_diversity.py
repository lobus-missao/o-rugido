"""Seleção de top-N com diversidade — evita 3 matérias da mesma história/editoria."""
from __future__ import annotations

from news_radar.services.editorial import _select_with_diversity


def _art(art_id: str, sig: str, cat: str, score: float) -> dict:
    return {
        "id": art_id,
        "title_signature": sig,
        "category": cat,
        "final_score_piaui": score,
    }


class TestSelectWithDiversity:
    def test_lista_vazia_retorna_vazio(self):
        assert _select_with_diversity([], 3) == []

    def test_top_zero_retorna_vazio(self):
        candidates = [_art("a", "sig1", "Política", 80)]
        assert _select_with_diversity(candidates, 0) == []

    def test_evita_mesma_history(self):
        # Três candidatos com a MESMA title_signature → só o primeiro entra
        candidates = [
            _art("a", "operacao_pf", "Política", 90),
            _art("b", "operacao_pf", "Política", 85),
            _art("c", "operacao_pf", "Política", 80),
        ]
        result = _select_with_diversity(candidates, 3)
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_evita_mesma_categoria_no_primeiro_passe(self):
        # 3 de política + 1 de saúde → política só 1, saúde 1, total 2 no 1º passe
        candidates = [
            _art("a", "sig1", "Política", 90),
            _art("b", "sig2", "Política", 85),
            _art("c", "sig3", "Política", 80),
            _art("d", "sig4", "Saúde", 70),
        ]
        result = _select_with_diversity(candidates, 3)
        # 1º passe: a (Política) + d (Saúde) = 2
        # 2º passe: relaxa categoria → b (Política, sig2 nova) entra
        assert len(result) == 3
        assert {r["id"] for r in result} == {"a", "d", "b"}

    def test_respeita_ordem_de_score(self):
        candidates = [
            _art("a", "sig1", "Política", 95),
            _art("b", "sig2", "Economia", 85),
            _art("c", "sig3", "Saúde", 75),
        ]
        result = _select_with_diversity(candidates, 3)
        assert [r["id"] for r in result] == ["a", "b", "c"]

    def test_sem_categoria_so_dedupa_history(self):
        # Sem category, deve só evitar mesma signature
        candidates = [
            _art("a", "sig1", "", 90),
            _art("b", "sig2", "", 85),
            _art("c", "sig1", "", 80),  # mesma sig de a
            _art("d", "sig3", "", 75),
        ]
        result = _select_with_diversity(candidates, 3)
        assert {r["id"] for r in result} == {"a", "b", "d"}

    def test_top_maior_que_disponivel(self):
        candidates = [_art("a", "sig1", "Política", 90)]
        result = _select_with_diversity(candidates, 5)
        assert len(result) == 1
