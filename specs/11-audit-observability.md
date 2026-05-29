# Spec 11 — Auditoria e Observabilidade

**Status:** Básico — evoluir na Fase 8
**Fase:** 8

---

## Estado Atual

- `feed_runs` — log de coletas por fonte
- `dispatches` — rastreabilidade de quem aprovou artigo e card
- `ai_batches` — histórico de lotes com status, contagens, erros
- `pages/1_Operacao.py` — exibe log de coletas e métricas básicas
- `pages/7_Alertas.py` — alertas computados em tempo real

---

## Logs de Coleta

**Onde:** tabela `feed_runs`

```sql
SELECT source, status, collected_count, error, started_at, finished_at
FROM feed_runs
ORDER BY id DESC
LIMIT 100;
```

**Estados:** `ok` | `warning` | `error`

**Dashboard:** `1_Operacao.py` exibe últimas 100 coletas com filtro por status.

**Alerta:** fonte com ≥3 erros consecutivos (futuro: alertar na página de alertas).

---

## Logs de Classificação / Ranking

**Onde:** `articles.score_reasons_json` (JSONB)

```json
["órgãos/vida pública: 3", "risco/investigação: 2", "termos Piauí: 1", "recente: <6h"]
```

**Acesso:** `3_Ranking.py` pode exibir via expander.

---

## Logs de Importação IA

**Onde:** tabela `ai_batches` + arquivos `data/ai_results/{batch_id}.result.json`

```sql
SELECT batch_id, scope, status, imported_count, ignored_count, error, completed_at
FROM ai_batches ORDER BY created_at DESC;
```

**Dashboard:** `2_Lotes_IA.py` exibe histórico de lotes e log detalhado por artigo após importação.

---

## Logs de Aprovação

**Onde:** tabela `dispatches`

```sql
SELECT d.id, a.title, d.edition, d.status,
       d.article_reviewed_by, d.article_reviewed_at,
       d.card_reviewed_by, d.card_reviewed_at
FROM dispatches d JOIN articles a ON d.article_id = a.id
ORDER BY d.created_at DESC;
```

**Dashboard:** `0_Edicoes.py` exibe status e revisores por dispatch.

---

## Tabela de Auditoria Formal (Futuro — Fase 8)

```sql
editorial_actions (
    id SERIAL PK,
    article_id TEXT,
    dispatch_id INTEGER,
    action TEXT NOT NULL,       -- approve_article | reject_article | approve_card | reject_card |
                                --  ai_import | card_generate | status_change | manual_edit
    actor TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    notes TEXT,
    metadata JSONB,             -- payload extra da ação
    created_at TIMESTAMPTZ DEFAULT NOW()
)
```

**Eventos a registrar:**
- Aprovação/rejeição de artigo
- Aprovação/rejeição de card
- Importação de lote IA (resultado por artigo)
- Geração de card
- Mudança manual de status editorial
- Mudança manual de prioridade

---

## Rastreabilidade

**Cadeia atual:**
```
articles.created_at           → quando capturado
feed_runs.started_at          → quando a fonte foi coletada
ai_batches.created_at         → quando lote foi gerado
ai_batches.completed_at       → quando lote foi importado
dispatches.created_at         → quando edição foi criada
dispatches.article_reviewed_at → quando artigo foi revisado
dispatches.card_reviewed_at   → quando card foi revisado
dispatches.ready_at           → quando ficou pronto para publicar
```

---

## Métricas Básicas

Disponíveis via `repository.stats()`:

```python
{
    "total_articles": int,
    "articles_with_ai": int,
    "ai_batches": {"pending": N, "completed": N, "failed": N},
    "feed_runs": [last 30 runs]
}
```

**Futuros:**
- Tempo médio de ciclo (captura → publicação)
- Percentual de aprovação vs rejeição
- Cobertura de IA por escopo e período
- Fontes mais produtivas
- Score médio por escopo

---

## Logs de Erro

**Coleta:** `feed_runs.error` (truncado em 500 chars)
**IA:** `ai_batches.error`
**Card:** logado mas não persistido formalmente (futuro: adicionar campo)
**Dispatch:** erros de Telegram logados no terminal/processo

---

## Observabilidade da Dashboard

**Dashboard `7_Alertas.py` atual:**
- Artigos críticos sem IA
- Fontes com erro recente
- Lotes expirados

**Futuro:**
- Tempo desde última coleta bem-sucedida por fonte
- Lotes pendentes há mais de X horas
- Dispatches sem ação há mais de Y horas
- Artigos alta prioridade sem card

---

## Critérios de Aceite

- [ ] Toda coleta de feed tem registro em `feed_runs`
- [ ] Toda aprovação/rejeição tem registro com ator e timestamp
- [ ] Toda importação de IA tem log de contagem de atualizados/ignorados
- [ ] Dashboard mostra alertas para fontes com erro
- [ ] Dashboard mostra lotes pendentes há mais de 24h
