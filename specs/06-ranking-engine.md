# Spec 06 — Motor de Ranking

**Status:** Funcional — documentar e evoluir
**Fase:** 6 (configurável) / Atual funciona

---

## Estado Atual

Ranking automático em `ranker.py::automatic_scores()`. Funciona e está em produção. Esta spec documenta e propõe evolução sem quebrar o que existe.

---

## Scores Automáticos (Atual)

Calculados por `automatic_scores(article)` em `ranker.py`.

### Dimensões por Contagem de Termos

| Dimensão | Variável | Peso atual | Cap |
|----------|----------|-----------|-----|
| Órgãos públicos | `public_count` | ×3 | 12 |
| Risco/investigação | `risk_count` | ×4 | 16 |
| Dinheiro público | `money_count` | ×3 | 12 |
| Impacto social | `social_count` | ×2 | 8 |
| Política | `political_count` | ×2 | 8 |
| Valor monetário | `money_values` | 6 flat | — |
| Confiança da fonte | `trust` | ×6 | 6 |
| Recência | `novelty` (0–10) | ×1 | 10 |
| Riqueza de conteúdo | `summary_len` | 0–6 | 6 |

### Bônus Geográficos

| Geográfico | Bônus | Cap |
|-----------|-------|-----|
| Brasil terms | ×4 | 16 |
| Piauí terms | ×7 | 28 |
| Teresina terms | ×9 | 36 |
| source_scope == 'piaui' | +10 piaui_bonus | — |
| source_scope == 'teresina' | +10 piaui_bonus, +14 teresina_bonus | — |

### Penalidade para Notícia Nacional em Rankings Locais

```python
# Se artigo nacional sem menção a Piauí/Teresina
if piaui_count == 0 and teresina_count == 0 and source_scope == "brasil":
    score_piaui *= 0.55
    score_teresina *= 0.35
```

### Fórmula Base

```python
common = (base_content + base_public + base_risk + base_money +
          base_social + base_political + base_money_value + base_trust + base_novelty)

score_brasil = clamp(common + brasil_bonus, 0, 100)
score_piaui = clamp(common + piaui_bonus, 0, 100)
score_teresina = clamp(common + piaui_bonus * 0.55 + teresina_bonus, 0, 100)
```

---

## Score de IA

Calculado por `ranker.py::ai_score_from_payload()`.

### Campos IA (modernos)
```python
modern_fields = ["interesse_publico", "impacto_social", "urgencia",
                 "relevancia_local", "dinheiro_publico"]
```

### Campos IA (legados — compatibilidade)
```python
legacy_fields = ["impacto_publico", "gravidade", "relevancia_politica",
                 "risco_investigativo", "dinheiro_publico"]
```

### Cálculo
```python
ai_score = clamp((sum(values) / len(values)) * 10)
# Escala: 0-10 dos campos → × 10 → 0-100
```

---

## Score Final (Combinação Auto + IA)

```python
# ranker.py::combine_with_ai()
final_score = round(clamp(auto_score * 0.58 + ai_score * 0.42), 2)
```

Se `ai_score is None`: `final_score = auto_score`.

---

## Campos de Score no Banco

| Campo | Descrição |
|-------|-----------|
| `auto_score_brasil` | Score automático escopo Brasil |
| `auto_score_piaui` | Score automático escopo Piauí |
| `auto_score_teresina` | Score automático escopo Teresina |
| `final_score_brasil` | Score final Brasil (com IA se disponível) |
| `final_score_piaui` | Score final Piauí |
| `final_score_teresina` | Score final Teresina |
| `ai_score` | Score calculado da resposta IA |
| `score_reasons_json` | JSONB com lista de razões do score automático |

---

## Dimensões Descritas (para prompt IA)

| Dimensão | Escala | Descrição |
|----------|--------|-----------|
| `interesse_publico` | 0–10 | Quanto afeta vida dos cidadãos, serviços públicos, direitos |
| `impacto_social` | 0–10 | Saúde, educação, transporte, segurança, moradia diretamente afetados |
| `gravidade` | 0–10 | Severidade do fato (crime, crise, risco coletivo) |
| `risco_investigativo` | 0–10 | Potencial de irregularidade, denúncia, investigação |
| `dinheiro_publico` | 0–10 | Contratos, licitações, desvios, verbas, obras |
| `relevancia_politica` | 0–10 | Envolvimento de mandatários, partidos, eleições, mandatos |
| `polemica` | 0–10 | Assunto gera debate público, polarização, repercussão |
| `urgencia` | 0–10 | Fato novo, crise imediata, interrupção de serviço |
| `relevancia_local` | 0–10 | Impacto direto em Piauí, Teresina ou municípios piauienses |
| `confiabilidade` | 0–10 | Credibilidade da fonte, verificabilidade do fato |
| `prioridade_final` | texto | Síntese: ruido | baixa | media | alta | critica |

---

## Recência

```python
def recency_score(published_at):
    if hours <= 6:   return 10
    if hours <= 24:  return 8
    if hours <= 72:  return 6
    if hours <= 168: return 4
    return 1
```

---

## Evolução Futura (Fase 6)

### Score Configurável pela Dashboard

```sql
-- Tabela score_weights
(scope, dimension, weight, max_contribution)

-- Exemplos
('brasil', 'risk', 1.5, 24)  -- aumentar peso de risco
('teresina', 'social', 2.0, 16)  -- priorizar impacto social local
```

Dashboard > Configurações permitirá ajustar pesos por dimensão e escopo.

### Score Manual do Editor

Campo futuro em `articles`:
```sql
editor_score_override NUMERIC,  -- override manual pelo editor
editor_score_reason TEXT,
editor_score_by TEXT,
editor_score_at TIMESTAMPTZ
```

Quando preenchido: `final_score = editor_score_override` (bypass total da fórmula).

### Histórico de Scores

Tabela futura:
```sql
score_history (article_id, score_type, score_value, calculated_at, trigger_reason)
```

---

## Testes Obrigatórios da Fórmula

```python
# tests/test_ranking_and_ai_smoke.py — expandir
def test_auto_score_zero_for_empty_article():
    scores = automatic_scores({"title": "", "summary": "", "source_scope": "brasil"})
    assert scores["auto_score_brasil"] == 0

def test_teresina_article_ranks_higher_locally():
    teresina_art = {"title": "Prefeitura de Teresina lança edital", "source_scope": "teresina", ...}
    brasil_art = {"title": "Lula fala sobre economia", "source_scope": "brasil", ...}
    scores_t = automatic_scores(teresina_art)
    scores_b = automatic_scores(brasil_art)
    assert scores_t["final_score_teresina"] > scores_b["final_score_teresina"]

def test_ai_score_combined_correctly():
    combined = combine_with_ai(auto_score=60, ai_score=80)
    expected = round(60 * 0.58 + 80 * 0.42, 2)
    assert combined == expected
```

---

## Critérios de Aceite

- [ ] `auto_score_*` nunca negativo, nunca > 100
- [ ] Artigo local (teresina) > artigo nacional no ranking de Teresina
- [ ] `final_score` com IA sempre diferente de apenas auto_score
- [ ] `score_reasons_json` preenchido com razões legíveis
- [ ] Recálculo de ranking via CLI atualiza todos os artigos em lote
