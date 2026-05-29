# Diagnóstico do Projeto — News Radar RSS

> Auditoria baseada na análise direta do código-fonte em 2026-05-29.

---

## 1. O Que o Projeto Faz Hoje

O News Radar RSS é uma plataforma editorial de monitoramento de notícias com foco em Piauí, Teresina e Brasil. O sistema captura notícias via RSS, aplica ranking automático por palavras-chave, permite análise assistida por IA externa (fluxo manual: prompt → ChatGPT/Claude → JSON → importação), gera cards visuais PNG via template HTML + Playwright, e organiza um fluxo editorial com aprovação por Telegram.

---

## 2. Arquitetura Atual Encontrada

```
configs/feeds.yaml         → 57 feeds RSS configurados (brasil, piaui, teresina)
src/news_radar/
  config.py                → paths, env vars, DATABASE_URL
  db.py                    → schema SQL, connect(), init_db(), migrações inline
  collector.py             → parse RSS, upsert artigos, log feed_runs
  ranker.py                → scoring automático por termos, recência, confiança
  repository.py            → top_articles(), stats(), update_card_status()
  ai_batches.py            → make_ai_batches(), import_ai_result(), list/get
  ai_caller.py             → integração com Ollama (não usada no fluxo principal)
  card_renderer.py         → HTML template → Playwright → PNG
  dispatch.py              → edições morning/noon/evening → Telegram approval
  telegram_sender.py       → funções de envio direto ao Telegram
  text_utils.py            → canonicalize_url, title_signature, strip_html, count_terms
  score_explainer.py       → (existe, mas não integrado ao dashboard principal)
  dash_utils.py            → componentes Streamlit reutilizáveis
  dashboard_queries.py     → queries específicas para dashboard
  cli.py                   → CLI com todos os comandos
api_server.py              → Flask na porta 8888, bridge n8n ↔ CLI/Python
dashboard.py               → entrada Streamlit (página Radar)
pages/                     → 9 páginas do dashboard multipage
  0_Edicoes.py             → controle de edições e dispatches
  1_Operacao.py            → saúde do pipeline, ações, log de coletas
  2_Lotes_IA.py            → geração e importação de lotes IA
  3_Ranking.py             → visualização de ranking
  4_Clusters.py            → agrupamento (UI existe, backend incompleto)
  5_Editorial.py           → mesa editorial
  6_Entidades.py           → extração de entidades
  7_Alertas.py             → alertas editoriais
  8_Fontes_RSS.py          → gerenciamento de fontes
templates/card.html        → template HTML com placeholders {{variavel}}
prompts/ai_batch_prompt_template.txt → template de prompt para IA
data/ai_batches/           → prompts + payloads gerados
data/ai_results/           → JSONs de resposta da IA importados
data/cards/                → PNGs gerados
scripts/                   → scripts utilitários n8n, migrações, telegram_poller
n8n/workflows/             → 2 workflows: coleta (30min) e dispatch (3x/dia)
docker-compose.yml         → postgres + app + dashboard + n8n + caddy
```

---

## 3. Banco de Dados

**Tipo:** PostgreSQL (psycopg2-binary, sem ORM)
**URL padrão:** `postgresql://news:senha@localhost:5432/news_radar`

### Tabelas existentes:

#### `articles`
Tabela central. Contém tudo: raw_json, scores automáticos, scores IA, ai_json, status editorial, card_status, card_path, entidades, categorias, localidade.

Campos-chave:
- `id` TEXT PK — hash derivado de canonical_url + título
- `canonical_url` UNIQUE — deduplicação por URL
- `title_signature` — deduplicação fuzzy por título
- `source_scope` — "brasil" | "piaui" | "teresina"
- `source_trust` — 0.0–1.0
- `auto_score_brasil/piaui/teresina` — score automático por termos
- `final_score_brasil/piaui/teresina` — score final (auto × 0.58 + ai × 0.42)
- `ai_score` — score calculado a partir do JSON da IA
- `ai_json` JSONB — resposta completa da IA
- `editorial_status` — discovered | needs_ai | ai_done | selected | sent_to_telegram | approved | rejected | ready_to_publish | published | archived | card_rejected
- `card_status` — none | pending | approved | rejected
- `raw_json` JSONB — entrada bruta do RSS

#### `feed_runs`
Log de cada execução de coleta por fonte. Contém: source, url, status, collected_count, error, started_at, finished_at.

#### `ai_batches`
Controle de lotes de IA. Contém: batch_id, scope, status (pending/completed/failed/expired), article_count, prompt_path, payload_path, result_path, imported_count, ignored_count.

#### `dispatches`
Fluxo editorial por edição. Contém: article_id, edition (morning/noon/evening), edition_date, rank (1–3), scope, status do workflow de aprovação, message_ids do Telegram, revisores, timestamps.

Status do dispatch: pending_article → article_approved → pending_card → ready_to_publish → published (ou article_rejected / card_rejected).

---

## 4. Fluxo Atual de Ingestão

```
feeds.yaml (57 feeds)
    ↓
collector.collect_feeds()
    ↓
feedparser.parse(url)
    ↓ por entrada
normalize_entry() → strip_html, canonicalize_url, title_signature, date parse
    ↓
ranker.automatic_scores() → 9 dimensões de score por termos
    ↓
upsert_article() → dedup por canonical_url, fallback title_signature
    ↓
feed_runs INSERT (log)
```

Disparado por:
- CLI: `python -m news_radar.cli collect`
- API: `POST /pipeline/collect`
- n8n: workflow 01 a cada 30min

---

## 5. Fluxo Atual de Classificação / Ranking

**Automático (ao coletar):**
- 9 dimensões: public_org_terms, risk_terms, money_public_terms, social_impact_terms, political_terms, brazil_terms, piaui_terms, teresina_terms + recency
- Bônus por fonte local (source_scope), por termos geográficos
- Penalidade para notícia nacional sem menção local nos rankings locais
- Score normalizado 0–100

**Com IA (após importação):**
- IA retorna: interesse_publico, impacto_social, urgencia, relevancia_local, dinheiro_publico (0–10 cada)
- ai_score = média × 10
- final_score = auto × 0.58 + ai × 0.42

**Recálculo manual:**
- CLI: `python -m news_radar.cli rank`
- API: `POST /pipeline/rank`

---

## 6. Fluxo Atual de IA Assistida

```
Dashboard > Lotes IA
    ↓
Gerar lote → make_ai_batches(scope, top, batch_size, days_back)
    ↓
Salva em data/ai_batches/{batch_id}.prompt.txt e .json
    ↓
Usuário copia prompt da UI
    ↓
Cola no ChatGPT ou Claude
    ↓
Copia resposta JSON
    ↓
Cola na UI (textarea)
    ↓
Validação: JSON válido? IDs batem ≥40%?
    ↓
Import → import_ai_result_detailed()
    ↓
Atualiza: ai_score, ai_json, category, locality, priority, entities_json, final_scores
    ↓
Marca batch como completed
```

Funciona. É o fluxo central do produto. Já tem validação de IDs, log detalhado por artigo, percentual de match.

---

## 7. Fluxo Atual de Dashboard

Streamlit multipage em `dashboard.py` + `pages/`:

| Página | Função | Status |
|--------|--------|--------|
| Radar (main) | Artigos filtrados por período, escopo, prioridade, IA, busca | ✅ Funciona |
| 0_Edicoes | Controle de dispatches, edições morning/noon/evening | ✅ Funciona |
| 1_Operacao | Saúde do pipeline, ações, log de coletas | ✅ Funciona |
| 2_Lotes_IA | Geração e importação de lotes IA | ✅ Funciona (fluxo principal) |
| 3_Ranking | Visualização de ranking por escopo | Implementado |
| 4_Clusters | Agrupamento | UI parcial, backend incompleto |
| 5_Editorial | Mesa editorial | Implementado |
| 6_Entidades | Extração de entidades | Implementado |
| 7_Alertas | Alertas editoriais | Implementado |
| 8_Fontes_RSS | Gestão de fontes | Implementado |

---

## 8. Fluxo Atual com n8n

n8n é usado **apenas como scheduler HTTP**. Toda lógica está no Python.

**Workflow 01 (a cada 30min):**
```
POST /pipeline/collect {"limit_per_feed": 30}
POST /pipeline/rank
```

**Workflow 02 (06:30 / 11:30 / 17:30):**
```
POST /api/dispatch/run {"edition": "morning|noon|evening", "scope": "piaui", "top": 3}
```

**Ponto de acoplamento:** n8n precisa estar rodando para coleta e dispatch automáticos funcionarem. Se n8n cair, coleta para.

**Alternativa existente:** Tudo pode ser chamado diretamente via CLI ou API sem n8n.

---

## 9. Fluxo Atual com Telegram

Dois modos de operação (mutuamente exclusivos):

**Estratégia A — MVP local (atual):**
- `scripts/telegram_poller.py` faz polling `getUpdates`
- Processa callbacks de botões inline (approve/reject artigo e card)
- Roda como processo separado

**Estratégia B — Produção:**
- Webhook Telegram → n8n → `POST /api/telegram/callback`
- Endpoint existe mas não é usado no MVP

Fluxo: dispatch envia artigo com botões → editor clica → poller captura callback → chama `dispatch.handle_callback_action()` → aprova/rejeita → gera card → envia card → editor aprova card → status `ready_to_publish`.

---

## 10. Fluxo Atual de Cards / Imagens

```
dispatch.approve_article() ou dashboard
    ↓
card_renderer.render_cards(scope, limit, article_ids)
    ↓
Lê templates/card.html
    ↓
_render_html() → substitui {{placeholders}} com dados do artigo
    ↓
Playwright: browser.new_page(viewport 600x400)
    ↓
page.set_content(html)
    ↓
page.locator("#card").screenshot(path)
    ↓
Salva PNG em data/cards/card_{id[:16]}.png
    ↓
update_card_status(article_id, "pending", card_path)
```

Funciona com Playwright instalado. Dependência externa real.

---

## 11. Pontos Fortes

1. **Lógica de negócio 100% no Python** — n8n é só scheduler
2. **AI assistida sem dependência de API paga** — fluxo manual funciona
3. **Score multidimensional** — 3 escopos geográficos independentes
4. **Deduplicação dupla** — canonical_url + title_signature
5. **CLI completo** — cada operação pode ser chamada isoladamente
6. **API Flask** — integração com qualquer sistema externo
7. **Geração de card real** — HTML + Playwright + PNG já funcionando
8. **Dashboard multipage** — controle editorial já centralizado
9. **Fluxo de aprovação** — estados claros, rastreabilidade básica por dispatch
10. **Dados brutos preservados** — raw_json + prompts + results salvos em arquivo

---

## 12. Pontos Frágeis

1. **Clustering incompleto** — `4_Clusters.py` existe mas backend não implementa agrupamento real por similaridade textual
2. **Deduplicação limitada** — title_signature é hash de palavras, pode colidir; sem similaridade semântica
3. **Schema monolítico em `articles`** — tabela cresceu com tudo: scores, IA, card, editorial. Risco de rigidez.
4. **Playwright como dependência crítica** — se Playwright falhar, geração de cards quebra todo o dispatch
5. **Poller Telegram frágil** — processo separado, sem supervisão automática
6. **Sem auditoria formal** — `editorial_status` atualizado inline sem histórico de quem/quando/por quê
7. **Sem tabela de fontes gerenciável** — fontes em YAML, sem CRUD via dashboard
8. **`ai_caller.py` (Ollama) não integrado** — existe mas não é usado no fluxo principal
9. **Sem retentativas de coleta** — se feedparser falha, não há retry automático
10. **Sem validação de schema** — `ai_json` é JSONB sem enforcement de campos obrigatórios
11. **Score formula hardcoded** — pesos não configuráveis pela dashboard sem alterar código
12. **`score_explainer.py` existe mas não exibido** — feature incompleta
13. **Migrations inline em `init_db()`** — MIGRATION_SQL roda sempre; sem versionamento formal

---

## 13. Riscos Técnicos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| n8n cai → coleta para | Alta | Alto | Adicionar scheduler Python interno |
| Playwright sem Chromium | Média | Alto | Verificar instalação, fallback sem screenshot |
| PostgreSQL sem backup | Baixa | Crítico | Documentar backup regular |
| title_signature colisão | Média | Médio | Prefere canonical_url, colisão não apaga dados |
| Prompts em arquivo grande | Baixa | Médio | Já compactado em compact_article() |
| Telegram API mudança | Baixa | Alto | Abstrair em telegram_sender.py |

---

## 14. Pontos de Acoplamento com n8n

| Acoplamento | Criticidade | Substituição |
|-------------|-------------|--------------|
| Coleta RSS a cada 30min | Alta | APScheduler / cron / CLI agendado |
| Dispatch editorial 3x/dia | Alta | APScheduler / cron / botão no dashboard |
| Nenhum fluxo de negócio no n8n | N/A | — n8n já é só scheduler |

**Conclusão:** desacoplamento do n8n é seguro porque toda lógica já está no Python. Basta adicionar scheduler interno.

---

## 15. Oportunidades de Melhoria

1. **Scheduler interno** (APScheduler) para eliminar dependência do n8n
2. **Clustering por similaridade** (TF-IDF, hash simhash, ou embedding leve)
3. **Tabela `sources`** com CRUD via dashboard, substituindo feeds.yaml
4. **Histórico de status editorial** (tabela `editorial_status_history`)
5. **Score configurável** pela dashboard (pesos por dimensão)
6. **Auditoria formal** — registrar toda ação com usuário, timestamp, contexto
7. **Retry automático** em coleta de feeds com erro
8. **Validação de schema do ai_json** antes de importar
9. **Preview do card** antes de aprovar
10. **Integrar score_explainer.py** na visualização de artigos

---

## 16. O Que Não Deve Ser Mexido Agora

- Toda a lógica de `ranker.py` (funciona e foi ajustada)
- O fluxo de importação de IA em `ai_batches.py` (funciona end-to-end)
- O template `templates/card.html` (em produção)
- O schema das tabelas principais (migrations incrementais obrigatórias)
- O CLI (`cli.py`) — interface estável entre componentes
- Os workflows n8n existentes (enquanto não substituídos por scheduler interno)
- O poller Telegram (`telegram_poller.py`)
- A estrutura de diretórios `data/` (arquivos gerados em produção)
