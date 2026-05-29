# Skill — Padrões de Testes e Revisão (News Radar)

Referência para agentes escrevendo testes ou fazendo revisão de código.

---

## Estrutura de Testes Existente

```
tests/
  conftest.py                    → fixtures compartilhadas
  test_api_smoke.py              → smoke tests da API Flask
  test_collector_smoke.py        → smoke tests do collector
  test_db_and_card_smoke.py      → smoke tests de banco e cards
  test_dispatch_flow_smoke.py    → smoke tests do fluxo de dispatch
  test_ranking_and_ai_smoke.py   → smoke tests de ranking e IA
```

---

## Regra: Cada Critério de Aceite Tem Teste

Para cada spec, cada critério de aceite deve ter:
1. Teste automatizado em `tests/test_*.py`, OU
2. Validação manual documentada (checklist em `docs/`)

---

## Estrutura de Teste Padrão

```python
# tests/test_ranking_and_ai_smoke.py
import pytest
from news_radar.ranker import automatic_scores, combine_with_ai, ai_score_from_payload

def test_auto_score_not_negative():
    """Score automático nunca negativo."""
    scores = automatic_scores({"title": "teste", "summary": "", "source_scope": "brasil", "source_trust": 0.5})
    assert scores["auto_score_brasil"] >= 0
    assert scores["auto_score_brasil"] <= 100

def test_teresina_article_ranks_higher_locally():
    """Artigo de Teresina deve ranquear mais alto em Teresina."""
    local = automatic_scores({
        "title": "Prefeitura de Teresina anuncia obras",
        "summary": "A Prefeitura de Teresina...",
        "source_scope": "teresina", "source_trust": 0.7
    })
    nacional = automatic_scores({
        "title": "Governo Federal anuncia investimentos",
        "summary": "O governo federal...",
        "source_scope": "brasil", "source_trust": 0.8
    })
    assert local["auto_score_teresina"] > nacional["auto_score_teresina"]

def test_combine_with_ai_formula():
    """Fórmula de combinação auto + IA."""
    result = combine_with_ai(auto_score=60.0, ai_score=80.0)
    expected = round(60.0 * 0.58 + 80.0 * 0.42, 2)
    assert result == expected

def test_combine_without_ai():
    """Sem IA, retorna auto_score."""
    assert combine_with_ai(60.0, None) == 60.0
```

---

## Testes de Importação de IA

```python
# tests/test_ranking_and_ai_smoke.py
def test_import_valid_json(tmp_path):
    """Importação de JSON válido deve atualizar artigos."""
    # Precisa de banco configurado (fixture de banco de teste)
    ...

def test_import_invalid_json(tmp_path):
    """JSON inválido deve retornar erro, não crashar."""
    path = tmp_path / "bad.json"
    path.write_text("{not valid json}", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        import_ai_result(str(path))

def test_import_wrong_ids(tmp_path):
    """IDs que não existem no banco devem ser ignorados."""
    path = tmp_path / "wrong.json"
    path.write_text('[{"id": "nao_existe_no_banco", "prioridade": "alta"}]')
    result = import_ai_result(str(path))
    assert result["ignored"] == 1
    assert result["updated"] == 0
```

---

## Testes de Status Editorial

```python
def test_dispatch_status_transitions():
    """Verificar que aprovação muda status corretamente."""
    # pending_article → article_approved (após approve_article)
    # article_approved → pending_card (após generate_card)
    # pending_card → ready_to_publish (após approve_card)
    ...
```

---

## Testes de Deduplicação

```python
def test_same_url_no_duplicate():
    """Mesmo canonical_url não gera novo artigo."""
    ...

def test_same_title_signature_no_duplicate():
    """Mesmo title_signature não gera novo artigo."""
    ...
```

---

## Testes de Geração de Card

```python
@pytest.mark.skipif(
    not shutil.which("chromium-browser"),
    reason="Playwright/Chromium não instalado"
)
def test_card_generates_png(tmp_path):
    """Card PNG gerado com dados mínimos."""
    ...
```

---

## Fixture Compartilhada (`conftest.py`)

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_article():
    return {
        "id": "abc123",
        "title": "Prefeitura anuncia licitação",
        "url": "https://exemplo.com/noticia/1",
        "canonical_url": "https://exemplo.com/noticia/1",
        "source": "Cidade Verde",
        "source_scope": "piaui",
        "source_trust": 0.74,
        "summary": "A Prefeitura de Teresina abriu licitação...",
        "priority": "alta",
        "category": "Governos e politica",
        "ai_score": 7.5,
        "final_score_piaui": 72.0,
    }

@pytest.fixture
def sample_ai_response():
    return [
        {
            "id": "abc123",
            "editoria": "Governos e politica",
            "prioridade": "alta",
            "interesse_publico": 8,
            "impacto_social": 6,
            "urgencia": 7,
            "relevancia_local": 9,
            "dinheiro_publico": 8,
        }
    ]
```

---

## Review Agent — Checklist

Ao revisar uma implementação, verificar:

```
[ ] O código corresponde ao critério de aceite da spec relevante?
[ ] Migrations são incrementais (ADD COLUMN IF NOT EXISTS)?
[ ] Nenhum dado existente é apagado sem aprovação?
[ ] n8n não voltou a ter regra de negócio?
[ ] Comportamentos existentes (coleta, ranking, IA, card, dispatch) continuam funcionando?
[ ] Exceções são tratadas com log, não silenciadas?
[ ] Credenciais não aparecem no código?
[ ] Testes smoke ainda passam?
[ ] Código novo tem teste correspondente (ou validação manual documentada)?
[ ] Novos campos no banco têm índices quando necessário?
```

---

## Não Aprovar Mudança Fora da Spec

Se o código implementado faz algo não especificado em `specs/`:
1. Questionar se é necessário
2. Se sim: atualizar a spec antes de aprovar
3. Se não: reverter a mudança extra

Exceção: correções de bug óbvias que não alteram comportamento externo.

---

## Executar Testes

```bash
# Rodar todos os testes
python -m pytest tests/ -v

# Rodar teste específico
python -m pytest tests/test_ranking_and_ai_smoke.py -v

# Rodar com saída de print
python -m pytest tests/ -v -s
```
