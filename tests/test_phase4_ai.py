"""
Testes da Fase 4 — IA Assistida (validação e importação).

Verifica:
  1. validate_ai_item() — campos obrigatórios, range numérico, prioridade enum.
  2. validate_ai_response() — JSON inválido, match de IDs, thresholds.
  3. import_ai_result_detailed() — chama record_editorial_action após importação.

Ref: specs/07-ai-assisted-processing.md, skills/ai-prompt-import-patterns.md
"""
from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from news_radar.ai_batches import (
    NUMERIC_FIELDS,
    VALID_PRIORIDADE,
    validate_ai_item,
    validate_ai_response,
)
import news_radar.ai_batches as ab_module


# ===========================================================================
# Fixtures
# ===========================================================================

def _item(**kwargs) -> dict:
    """Item mínimo válido, sobrescrito pelos kwargs."""
    base = {
        "id": "abc123def456",
        "editoria": "Governos e politica",
        "categoria": "Licitação",
        "localidade": "Teresina",
        "entidades": ["Prefeitura de Teresina"],
        "interesse_publico": 8,
        "impacto_social": 7,
        "gravidade": 6,
        "risco_investigativo": 9,
        "dinheiro_publico": 8,
        "relevancia_politica": 5,
        "polemica": 4,
        "urgencia": 7,
        "relevancia_local": 9,
        "confiabilidade": 8,
        "prioridade": "alta",
        "resumo_curto": "Prefeitura licita R$12mi com indício de sobrepreço.",
        "titulo_sugerido": "Teresina paga 40% acima do mercado",
        "subtitulo_sugerido": "Licitação de R$12mi tem indícios de superfaturamento",
        "pontos_chave": ["R$12 milhões", "40% acima do mercado"],
        "tags": ["licitação", "Teresina"],
        "justificativa_score": "Alto risco investigativo e dinheiro público elevado",
    }
    base.update(kwargs)
    return base


EXPECTED_IDS = {"abc123def456", "def789ghi012", "xyz321uvw654"}


# ===========================================================================
# Testes de validate_ai_item
# ===========================================================================

def test_validate_ai_item_item_valido_nao_tem_erros():
    """Item completo e válido deve passar sem erros."""
    result = validate_ai_item(_item())
    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_ai_item_sem_id_falha():
    """Item sem 'id' deve falhar com erro descritivo."""
    item = _item()
    del item["id"]
    result = validate_ai_item(item)
    assert result["ok"] is False
    assert any("id" in e for e in result["errors"])


def test_validate_ai_item_id_vazio_falha():
    """Item com id='' deve falhar."""
    result = validate_ai_item(_item(id=""))
    assert result["ok"] is False


def test_validate_ai_item_campo_obrigatorio_ausente():
    """Cada campo obrigatório ausente deve gerar erro."""
    for field in ["editoria", "prioridade", "interesse_publico", "resumo_curto"]:
        item = _item()
        del item[field]
        result = validate_ai_item(item)
        assert result["ok"] is False, f"Deveria falhar com '{field}' ausente"
        assert any(field in e for e in result["errors"]), (
            f"Erro deveria mencionar '{field}': {result['errors']}"
        )


def test_validate_ai_item_score_acima_de_10_falha():
    """Score > 10 deve gerar erro de range."""
    result = validate_ai_item(_item(interesse_publico=11))
    assert result["ok"] is False
    assert any("interesse_publico" in e for e in result["errors"])


def test_validate_ai_item_score_abaixo_de_0_falha():
    """Score < 0 deve gerar erro de range."""
    result = validate_ai_item(_item(urgencia=-1))
    assert result["ok"] is False
    assert any("urgencia" in e for e in result["errors"])


def test_validate_ai_item_score_zero_valido():
    """Score = 0 é válido."""
    result = validate_ai_item(_item(interesse_publico=0))
    assert result["ok"] is True


def test_validate_ai_item_score_dez_valido():
    """Score = 10 é válido."""
    result = validate_ai_item(_item(interesse_publico=10))
    assert result["ok"] is True


def test_validate_ai_item_score_nao_numerico_falha():
    """Score não numérico deve gerar erro descritivo."""
    result = validate_ai_item(_item(impacto_social="alto"))
    assert result["ok"] is False
    assert any("impacto_social" in e for e in result["errors"])


def test_validate_ai_item_prioridade_invalida_falha():
    """Prioridade fora do enum deve falhar."""
    result = validate_ai_item(_item(prioridade="urgente"))
    assert result["ok"] is False
    assert any("prioridade" in e for e in result["errors"])


@pytest.mark.parametrize("prioridade", sorted(VALID_PRIORIDADE))
def test_validate_ai_item_prioridades_validas(prioridade):
    """Todas as prioridades válidas devem passar."""
    result = validate_ai_item(_item(prioridade=prioridade))
    assert result["ok"] is True, f"Prioridade '{prioridade}' deveria ser válida"


def test_validate_ai_item_nao_e_dict_falha():
    """Item que não é dict deve falhar."""
    result = validate_ai_item("string_invalida")  # type: ignore
    assert result["ok"] is False


def test_validate_ai_item_score_float_valido():
    """Score float como 7.5 é válido."""
    result = validate_ai_item(_item(interesse_publico=7.5))
    assert result["ok"] is True


def test_validate_ai_item_score_ausente_nao_gera_erro_de_range():
    """Campo numérico ausente não gera erro de range (só erro de 'obrigatório' se for required)."""
    item = _item()
    del item["gravidade"]  # não obrigatório, mas numérico
    result = validate_ai_item(item)
    errors = result["errors"]
    assert not any("fora do intervalo" in e and "gravidade" in e for e in errors)


# ===========================================================================
# Testes de validate_ai_response
# ===========================================================================

def _make_json(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False)


def test_validate_ai_response_json_invalido_falha():
    """JSON malformado deve retornar ok=False com mensagem de erro."""
    result = validate_ai_response("{not valid json", EXPECTED_IDS)
    assert result["ok"] is False
    assert "JSON inválido" in result["error"]
    assert result["can_import"] is False


def test_validate_ai_response_nao_lista_falha():
    """JSON que não é lista deve retornar ok=False."""
    result = validate_ai_response('{"id": "abc"}', EXPECTED_IDS)
    assert result["ok"] is False
    assert result["can_import"] is False


def test_validate_ai_response_lista_vazia_falha():
    """Lista vazia deve retornar ok=False."""
    result = validate_ai_response("[]", EXPECTED_IDS)
    assert result["ok"] is False


def test_validate_ai_response_match_alto_pode_importar():
    """Match >= 80% deve retornar can_import=True e match_pct correto."""
    items = [_item(id=i) for i in EXPECTED_IDS]
    result = validate_ai_response(_make_json(items), EXPECTED_IDS)
    assert result["ok"] is True
    assert result["match_pct"] == 100
    assert result["can_import"] is True
    assert result["matched"] == 3


def test_validate_ai_response_match_parcial_permite_importar():
    """Match entre 40-80% deve retornar can_import=True."""
    ids = list(EXPECTED_IDS)
    items = [_item(id=ids[0]), _item(id=ids[1])]  # 2 de 3 = 66%
    result = validate_ai_response(_make_json(items), EXPECTED_IDS)
    assert result["ok"] is True
    assert result["match_pct"] >= 40
    assert result["can_import"] is True


def test_validate_ai_response_match_baixo_bloqueia_importacao():
    """Match < 40% deve retornar can_import=False."""
    ids_set = set(list(EXPECTED_IDS)[:3])  # garante set para a chamada
    # Apenas 1 de 3 = 33%
    ids_list = list(ids_set)
    items = [_item(id=ids_list[0]), _item(id="id_desconhecido_1"), _item(id="id_desconhecido_2")]
    result = validate_ai_response(_make_json(items), ids_set)
    assert result["ok"] is True
    # match_pct deve ser baixo ou wrong_batch ativado
    assert result["match_pct"] < 40 or result["wrong_batch"] is True
    assert result["can_import"] is False


def test_validate_ai_response_ids_completamente_errados_bloqueia():
    """IDs que não pertencem ao lote devem bloquear importação."""
    items = [_item(id="id_errado_1"), _item(id="id_errado_2")]
    result = validate_ai_response(_make_json(items), EXPECTED_IDS)
    assert result["ok"] is True
    assert result["can_import"] is False


def test_validate_ai_response_strip_markdown_code_block():
    """Resposta com bloco de código markdown deve ser parseada corretamente."""
    items = [_item(id=i) for i in EXPECTED_IDS]
    content = "```json\n" + json.dumps(items) + "\n```"
    result = validate_ai_response(content, EXPECTED_IDS)
    assert result["ok"] is True
    assert result["matched"] == 3


def test_validate_ai_response_retorna_item_errors_para_campos_invalidos():
    """item_errors deve conter erros de campos inválidos."""
    items = [_item(id=id_, interesse_publico=15) for id_ in EXPECTED_IDS]
    result = validate_ai_response(_make_json(items), EXPECTED_IDS)
    assert result["ok"] is True
    assert len(result["item_errors"]) > 0
    assert any("interesse_publico" in e for e in result["item_errors"])


def test_validate_ai_response_sem_expected_ids_nao_crasha():
    """Validação sem IDs esperados não deve crashar."""
    items = [_item(id="qualquer")]
    result = validate_ai_response(_make_json(items), set())
    # match_pct = 0 quando não há IDs esperados, mas não deve lançar exceção
    assert isinstance(result, dict)


def test_validate_ai_response_conta_totais_corretamente():
    """total_result e total_expected devem refletir os valores corretos."""
    items = [_item(id=i) for i in EXPECTED_IDS]
    result = validate_ai_response(_make_json(items), EXPECTED_IDS)
    assert result["total_result"] == 3
    assert result["total_expected"] == 3


# ===========================================================================
# Testes de import_ai_result_detailed com record_editorial_action
# ===========================================================================

class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.executed: list = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def execute(self, q, p=None):
        self.executed.append((q, p or ()))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, cur): self._cur = cur
    def cursor(self): return self._cur
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


def _mk_connect(cur):
    @contextmanager
    def _connect():
        yield _FakeConn(cur)
    return _connect


def test_import_ai_result_detailed_chama_record_editorial_action_quando_atualiza(tmp_path):
    """import_ai_result_detailed deve chamar record_editorial_action quando atualiza artigos."""
    item = _item(id="abc123")
    result_file = tmp_path / "test.result.json"
    result_file.write_text(json.dumps([item]), encoding="utf-8")

    # Cursor que retorna o artigo na SELECT e não faz nada no UPDATE
    article_row = {
        "id": "abc123", "title": "Título teste", "source": "Fonte",
        "source_scope": "brasil", "auto_score_brasil": 50.0,
        "auto_score_piaui": 30.0, "auto_score_teresina": 20.0,
    }
    cur = _FakeCursor(rows=[article_row])

    with patch.object(ab_module, "connect", _mk_connect(cur)), \
         patch.object(ab_module, "_update_batch_status", return_value=None), \
         patch("news_radar.editorial.record_editorial_action") as mock_record:
        mock_record.return_value = 1
        result = ab_module.import_ai_result_detailed(
            result_file, batch_id="batch_test", actor="TestEditor"
        )

    # Verifica que a importação processou o artigo e registrou a ação editorial
    assert result["updated"] == 1
    assert "logs" in result
    mock_record.assert_called_once()
    call_kwargs = mock_record.call_args
    # Verifica campos-chave da chamada
    assert call_kwargs.kwargs.get("action") == "ai_import" or (
        call_kwargs.args and call_kwargs.args[0] == "ai_import"
    )


def test_import_ai_result_detailed_nao_chama_record_quando_nenhum_atualizado(tmp_path):
    """import_ai_result_detailed não deve chamar record_editorial_action se 0 artigos atualizados."""
    item = _item(id="id_que_nao_existe")
    result_file = tmp_path / "test.result.json"
    result_file.write_text(json.dumps([item]), encoding="utf-8")

    cur = _FakeCursor(rows=[None])  # SELECT retorna None → artigo não encontrado

    with patch.object(ab_module, "connect", _mk_connect(cur)), \
         patch("news_radar.editorial.record_editorial_action") as mock_record:
        result = ab_module.import_ai_result_detailed(result_file, batch_id=None, actor="Editor")

    # Com 0 atualizados, record_editorial_action não deve ser chamado
    mock_record.assert_not_called()
    assert result["updated"] == 0


def test_import_ai_result_detailed_aceita_json_invalido_com_excecao(tmp_path):
    """import_ai_result_detailed deve lançar exceção para JSON inválido."""
    result_file = tmp_path / "bad.result.json"
    result_file.write_text("{invalid json}", encoding="utf-8")

    with pytest.raises((json.JSONDecodeError, ValueError)):
        ab_module.import_ai_result_detailed(result_file)


def test_import_ai_result_detailed_arquivo_nao_encontrado():
    """import_ai_result_detailed deve lançar FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ab_module.import_ai_result_detailed("/caminho/que/nao/existe.json")


# ===========================================================================
# Testes de constantes e exportações
# ===========================================================================

def test_valid_prioridade_tem_cinco_valores():
    """VALID_PRIORIDADE deve ter exatamente 5 valores."""
    assert VALID_PRIORIDADE == {"ruido", "baixa", "media", "alta", "critica"}


def test_numeric_fields_inclui_campos_chave():
    """NUMERIC_FIELDS deve incluir todos os campos numéricos do prompt."""
    esperados = {
        "interesse_publico", "impacto_social", "urgencia",
        "relevancia_local", "dinheiro_publico", "gravidade",
        "risco_investigativo", "relevancia_politica", "polemica",
    }
    assert esperados.issubset(set(NUMERIC_FIELDS))
