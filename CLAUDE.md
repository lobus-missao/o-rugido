# CLAUDE.md — News Radar RSS

Documentação do projeto para sessões Claude Code. Leia antes de qualquer tarefa.
Para regras de agentes, papéis e fluxo de trabalho, veja também `AGENTS.md`.

---

## O que é este projeto

Plataforma editorial de monitoramento de notícias focada em Piauí, Teresina e Brasil. Captura RSS, aplica ranking automático multidimensional, permite análise por IA (fluxo manual — sem API paga), gera cards visuais HTML/PNG, e controla fluxo editorial com aprovação via dashboard Streamlit ou Telegram.

**Stack:** Python 3.12+ · PostgreSQL (psycopg2 direto, sem ORM) · Streamlit 1.40 · Flask 3.x · Playwright · APScheduler · n8n (scheduler externo opcional)

---

## Estrutura de diretórios

```
src/news_radar/          ← toda lógica de negócio
  config.py              ← paths, env vars, ensure_dirs()
  db.py                  ← schema SQL, init_db(), migrations versionadas, connect()
  collector.py           ← RSS → normalize → upsert
  ranker.py              ← scoring automático (9 dimensões), PIAUI_TERMS, TERESINA_TERMS
  repository.py          ← queries de leitura reutilizáveis
  ai_batches.py          ← make_batches, validate, import_result
  card_renderer.py       ← build_card_context → HTML → Playwright → PNG
  dispatch.py            ← fluxo editorial: approve/reject artigo e card, mark_published
  editorial.py           ← record_editorial_action, list_editorial_actions
  sources.py             ← CRUD de fontes RSS (tabela sources)
  clusters.py            ← clustering por título/entidades/keywords
  ranking.py             ← explain_cluster_score, score_summary, rank_clusters
  score_explainer.py     ← explain_score() — decomposição completa do score
  dashboard_queries.py   ← queries para dashboard (com @_ttl_cache para pesadas)
  dash_utils.py          ← sidebar_controls(), run_cli(), article_card(), PRIORITY_*
  scheduler.py           ← APScheduler interno (ativado via NEWS_RADAR_SCHEDULER=1)
  text_utils.py          ← canonicalize_url, title_signature, count_terms, normalize_text
  cli.py                 ← 16 subcomandos argparse
  ai_caller.py           ← integração Ollama (não usada no fluxo principal)
  telegram_sender.py     ← envio direto ao Telegram

api_server.py            ← Flask porta 8888 (bridge n8n ↔ Python)
dashboard.py             ← entrada Streamlit (página Radar principal)
pages/                   ← páginas multipage do dashboard
  0_Edicoes.py           ← controle de dispatches diários
  1_Operacao.py          ← saúde do pipeline
  2_Lotes_IA.py          ← geração e importação de lotes IA
  3_Ranking.py           ← visualização de ranking com score explainer
  4_Clusters.py          ← agrupamento de notícias similares
  5_Editorial.py         ← kanban editorial + geração de card
  6_Entidades.py         ← extração de entidades (ai_json)
  7_Alertas.py           ← alertas computados em tempo real
  8_Fontes_RSS.py        ← gestão de fontes (tabela sources)
  11_Auditoria.py        ← auditoria editorial (editorial_actions)
templates/               ← card.html, card-editorial-base.html
data/                    ← ai_batches/, ai_results/, cards/ (gerados)
configs/feeds.yaml       ← 57 feeds RSS configurados
scripts/                 ← seed_sources.py e utilitários
tests/                   ← test_phase2 … test_phase9, conftest
docs/                    ← OPERATIONS.md, DEPLOYMENT.md, checklist-e2e.md, specs
specs/                   ← specs por fase (00 a 13)
skills/                  ← guias de padrões por área
```

---

## Banco de dados

**Tabelas principais:**

| Tabela | Descrição |
|---|---|
| `articles` | Central. Contém scores, ai_json, card_status, editorial_status |
| `dispatches` | Fluxo editorial por edição (morning/noon/evening) |
| `feed_runs` | Log de cada coleta por fonte |
| `ai_batches` | Controle de lotes IA (pending/completed/failed) |
| `sources` | Fontes RSS gerenciáveis via dashboard |
| `editorial_actions` | Auditoria de todas as ações editoriais |
| `story_clusters` | Grupos de artigos similares |
| `cluster_articles` | Ligação N:N entre clusters e artigos |
| `schema_migrations` | Controle de versão de migrations (Fase 9) |

**Migrations:** Versionadas em `MIGRATION_SQL` (dict com chaves únicas). `init_db()` aplica apenas as pendentes via `schema_migrations`. Nunca remover entradas — só adicionar.

**Conexão:** Sempre via context manager `with connect() as conn:`. Commit automático ao sair sem exceção; rollback em exceção.

---

## Fluxo de dados principal

```
feeds.yaml (57 feeds)
  ↓ collector.collect_feeds()
  ↓ ranker.automatic_scores() → 9 dimensões de score
  ↓ upsert_article() → dedup por canonical_url + title_signature
  ↓ articles no banco

  ↓ [manual] make_ai_batches() → prompt → IA externa → import_ai_result()
  ↓ ai_score, ai_json, priority, category, locality, entities

  ↓ dispatch.create_dispatch() → envia ao Telegram (ou cria dry_run)
  ↓ approve_article() → gera card → approve_card() → ready_to_publish
  ↓ mark_published() → published
```

---

## Pontos críticos que NÃO devem ser alterados sem spec

1. **Fórmula de score:** `final = auto × 0.58 + ai × 0.42` — em `ranker.combine_with_ai()`
2. **Deduplicação:** `canonical_url` (UNIQUE) + `title_signature` (fuzzy) — `text_utils.py`
3. **Guard de idempotência do dispatch:** `create_dispatch()` verifica dispatch ativo antes de criar
4. **`editorial_status = 'approved'`** não era escrito pelo `dispatch.approve_article()` até Fase 8 — agora é. Usar `dispatches.status = 'article_approved'` para queries históricas.
5. **TERESINA_TERMS e PIAUI_TERMS** — removidos termos genéricos (zona norte/sul/leste/sudeste, fms, picos) na Fase 9. Não readicionar sem teste.

---

## Regras de desenvolvimento

1. **Migrations:** sempre `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Nunca DROP sem aprovação.
2. **Testes:** cada critério de aceite tem teste em `tests/test_phase*.py`. Não quebrar testes existentes.
3. **n8n:** não é o cérebro — toda lógica fica no Python. n8n chama endpoints Flask.
4. **Novas funções pesadas:** marcar com `@_ttl_cache(seconds=N)` em `dashboard_queries.py`.
5. **Playwright:** usar `_chromium_executable()` de `card_renderer.py` — não hardcodar path.
6. **Sem API de IA paga:** o fluxo é manual (prompt → clipboard → colar JSON).

---

## Testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Por fase
python -m pytest tests/test_phase7_cards.py -v
python -m pytest tests/test_phase8_approval.py -v

# Testes que requerem banco real (skipped por padrão)
TEST_DATABASE_URL=postgresql://... python -m pytest tests/ -v
```

Estado atual: **257 passed, 2 skipped** (os 2 skips requerem `TEST_DATABASE_URL`).

---

## CLI — referência rápida

```bash
python -m news_radar.cli init-db          # migrations pendentes
python -m news_radar.cli collect          # coletar RSS
python -m news_radar.cli rank             # recalcular scores
python -m news_radar.cli make-ai-batches  # gerar prompt para IA
python -m news_radar.cli import-ai        # importar JSON da IA
python -m news_radar.cli make-card        # gerar PNG
python -m news_radar.cli dispatch         # disparar edição
python -m news_radar.cli backup           # backup pg_dump
python -m news_radar.cli cleanup          # limpar artigos velhos
python -m news_radar.cli stats            # estatísticas do banco
python -m news_radar.cli cluster-articles # agrupar artigos
```

---

## Variáveis de ambiente

```
DATABASE_URL              # conexão PostgreSQL
TELEGRAM_BOT_TOKEN        # token do bot
TELEGRAM_CHAT_ID          # ID do canal/grupo
NEWS_RADAR_SCHEDULER      # 0=off (padrão), 1=APScheduler interno
NEWS_RADAR_DISPATCH_SCOPE # escopo do dispatch automático (piaui)
NEWS_RADAR_DRY_RUN        # 1=desativa envios reais ao Telegram
PLAYWRIGHT_BROWSERS_PATH  # onde playwright busca Chromium (/ms-playwright)
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH  # override de path do Chromium
```
