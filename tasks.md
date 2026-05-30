# tasks.md — Backlog Incremental por Fases

> Atualizado em: 2026-05-29
> Projeto: News Radar RSS

---

## Fase 0 — Diagnóstico e SDD ✅ Concluída

**Objetivo:** Criar base de Spec Driven Development adaptada ao projeto real.

### Tarefas
- [x] Analisar estrutura completa do projeto
- [x] Criar `docs/project-audit.md`
- [x] Criar `docs/target-architecture.md`
- [x] Criar `AGENTS.md`
- [x] Criar `specs/00` a `specs/13`
- [x] Criar `skills/` (6 arquivos)
- [x] Criar `prompts/` (6 arquivos)
- [x] Criar `templates/ai-batch-prompt-template.md`
- [x] Criar `templates/card-editorial-base.html`
- [x] Criar `tasks.md`

### Critérios de Aceite
- [x] Specs refletem o projeto real
- [x] Nenhum código foi alterado
- [x] n8n documentado como camada auxiliar
- [x] Arquivos criados conforme especificado

---

## Fase 1 — Desacoplamento Seguro do n8n

**Objetivo:** Sistema funcionar sem n8n obrigatório, usando scheduler interno Python.

### Tarefas
- [x] Guard de idempotência em `create_dispatch()` implementado (Fase 1 — pré-requisito do scheduler)
  - SQL: `COUNT(*) WHERE edition/edition_date/scope/status NOT IN (rejeitados)`
  - Retorna `[]` se edição ativa já existe; loga warning claro
  - Testes: `tests/test_dispatch_idempotency.py` (7 casos)
  - Docs: `docs/manual-validation-phase-1.md`
- [x] Adicionar `APScheduler>=3.10,<4.0` ao `requirements.txt`
- [x] Criar `src/news_radar/scheduler.py` com jobs de coleta e dispatch
  - `_job_collect_and_rank()` — collect_feeds + rank_all a cada 30 min
  - `_job_dispatch(edition, scope, top)` — cron 06:30 / 11:30 / 17:30
  - `start_scheduler()` — não inicia em contexto de teste, não inicia se desativado
  - `get_status()` — retorna estado + próximas execuções
  - `rank_all()` extraído para `ranker.py` (reutilizável, sem duplicação)
  - Testes: `tests/test_scheduler.py` (15 casos)
- [x] Integrar scheduler ao `api_server.py` (ativação via `NEWS_RADAR_SCHEDULER=1`)
  - Endpoint `GET /api/scheduler/status` adicionado
- [x] Atualizar `.env.example` com `NEWS_RADAR_SCHEDULER=0`, `NEWS_RADAR_DISPATCH_SCOPE`, `NEWS_RADAR_DISPATCH_TOP`
- [x] Dashboard `1_Operacao.py`: exibir status do scheduler e horários agendados
- [ ] Testar: desligar n8n, confirmar que coleta continua (validação manual pendente)
- [x] Documentar: `docs/N8N_WORKFLOWS.md` atualizado com seção sobre scheduler interno

### Riscos
- Duplo disparo se n8n e scheduler ativos simultâneo → **RESOLVIDO**: guard de idempotência
  implementado em `create_dispatch()`. Ativar scheduler interno só após este guard estar ativo.
- `collect_feeds()` já é idempotente por canonical_url (sem risco)

### Arquivos Prováveis
```
src/news_radar/scheduler.py  (novo)
api_server.py                (modificar — adicionar inicialização condicional)
requirements.txt             (adicionar APScheduler)
.env.example                 (adicionar variável)
pages/1_Operacao.py          (adicionar status do scheduler)
```

### Critérios de Aceite
- [ ] Coleta RSS funciona sem n8n rodando
- [ ] Dispatch editorial dispara 3x/dia sem n8n
- [ ] Ativação via variável de ambiente
- [ ] Testes smoke ainda passam

---

## Fase 2 — Fortalecimento do Banco / Modelo Editorial ✅ Concluída

**Objetivo:** Adicionar tabelas e campos que suportam auditoria, fontes gerenciáveis e histórico de status.

**Concluída em:** 2026-05-29

### Tarefas
- [x] Criar tabela `sources` em `SCHEMA_SQL` de `db.py`
- [x] Importar `feeds.yaml` para tabela `sources` (script de seed one-shot)
- [x] Criar tabela `editorial_actions` para auditoria
- [x] Criar `src/news_radar/sources.py` com helpers: `list_sources()`, `get_source_by_name()`, `upsert_source()`, `mark_source_success()`, `mark_source_error()`
- [x] Criar `src/news_radar/editorial.py` com: `record_editorial_action()`, `list_editorial_actions_for_target()`
- [x] Criar `scripts/seed_sources.py` (idempotente, suporte a --dry-run)
- [x] Criar `tests/test_phase2_sources.py` (20 testes unit + 1 smoke com TEST_DATABASE_URL)
- [ ] Registrar ações de aprovação/rejeição em `editorial_actions` (Fase 3 — integrar ao dispatch)
- [ ] Criar tabela `score_weights` (pesos configuráveis — Fase 6)
- [ ] Adicionar campo `editor_score_override` em `articles` (Fase 6)

### Arquivos Criados/Modificados
```
src/news_radar/db.py            (SCHEMA_SQL: tabelas sources + editorial_actions + índices)
src/news_radar/sources.py       (novo — repositório de fontes)
src/news_radar/editorial.py     (novo — registro de ações editoriais)
scripts/seed_sources.py         (novo — seed idempotente de feeds.yaml)
tests/test_phase2_sources.py    (novo — 21 testes)
```

### Critérios de Aceite
- [x] Tabelas criadas com `CREATE TABLE IF NOT EXISTS` (idempotente)
- [x] Collector continua funcionando com feeds.yaml (tabela sources é complementar, não substituta)
- [x] `sources` populada via `scripts/seed_sources.py` sem duplicidade (upsert por name)
- [x] `editorial_actions` registra eventos básicos via `record_editorial_action()`
- [x] 57 testes passando, 2 skipped (requerem TEST_DATABASE_URL)

### Como aplicar a migration
```bash
# Aplica automaticamente ao inicializar o banco
python -m news_radar.cli init-db

# Seed das fontes (57 feeds do feeds.yaml → tabela sources)
python scripts/seed_sources.py

# Dry-run para ver o que seria feito
python scripts/seed_sources.py --dry-run
```

### Como validar no banco
```sql
-- Verifica tabelas criadas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('sources', 'editorial_actions');

-- Conta fontes importadas
SELECT scope, COUNT(*) FROM sources GROUP BY scope ORDER BY scope;

-- Verifica ações editoriais
SELECT * FROM editorial_actions ORDER BY created_at DESC LIMIT 10;
```

---

## Fase 3 — Dashboard como Cockpit Editorial (Parte 1) ✅ Concluída

**Objetivo:** Transformar a dashboard em cockpit editorial inicial usando a base da Fase 2.

**Concluída em:** 2026-05-29

### Tarefas
- [x] `8_Fontes_RSS.py`: integrar dados da tabela `sources` — monitoramento por coleta (last_status, error_count, last_run_at)
- [x] `8_Fontes_RSS.py`: nova métrica "📦 Registradas no banco" + seção "Monitoramento via Banco"
- [x] `8_Fontes_RSS.py`: filtros e tabela de sources com fallback amigável quando tabela vazia
- [x] `1_Operacao.py`: métricas de fontes da tabela sources (total, habilitadas, com erro)
- [x] `1_Operacao.py`: seção "Ações Editoriais Recentes" com tabela das últimas 15 ações
- [x] `collector.py`: `_try_update_source_status()` — mark_source_success/error após cada feed
- [x] `dispatch.py`: `_try_record_editorial_action()` em approve_article, reject_article, approve_card, reject_card
- [x] `dashboard_queries.py`: `sources_summary()` e `recent_editorial_actions()`
- [x] `tests/test_phase3_integration.py` (13 testes novos — todos passam)

### Arquivos Alterados
```
src/news_radar/collector.py        (helper _try_update_source_status + chamada no loop)
src/news_radar/dispatch.py         (helper _try_record_editorial_action + 4 chamadas)
src/news_radar/dashboard_queries.py (sources_summary, recent_editorial_actions)
pages/8_Fontes_RSS.py              (integração tabela sources, 5ª métrica, seção banco)
pages/1_Operacao.py                (fontes banco + ações editoriais recentes)
tests/test_phase3_integration.py   (novo — 13 testes)
```

### Critérios de Aceite
- [x] Dashboard abre sem traceback
- [x] Página de fontes mostra dados da tabela sources com fallback amigável
- [x] Filtros funcionam
- [x] Coleta continua funcionando com feeds.yaml
- [x] Collector atualiza status da fonte quando fonte existir na tabela sources
- [x] Aprovação/rejeição registra ação editorial
- [x] Telegram continua compatível (sem alteração de comportamento)
- [x] n8n continua compatível
- [x] 70 testes passando, 2 skipped

### Pendente para Fase 3 continuação (Fase 4+)
- [ ] `5_Editorial.py`: botão "Gerar card" por artigo, botão "Marcar needs_ai"
- [ ] `0_Edicoes.py`: preview de card (`st.image()`) quando card_path existe
- [ ] Confirmação para ações destrutivas (rejeitar, arquivar) em Radar
- [ ] Editor opera ciclo completo sem terminal

---

## Fase 4 — IA Assistida com Prompt / Importação JSON ✅ Concluída

**Objetivo:** Fortalecer fluxo manual de IA: validação de campos, auditoria, UX aprimorada.

**Concluída em:** 2026-05-29

### Tarefas
- [x] Copiar prompt via `st.code()` com botão nativo do Streamlit
- [x] Exibir métricas do lote (tokens estimados, palavras, artigos)
- [x] Reimportação de lote já concluído com validação
- [x] `validate_ai_item()` — valida id, campos obrigatórios, range 0-10, prioridade enum
- [x] `validate_ai_response()` — valida JSON, ID match, item_errors por amostragem
- [x] `import_ai_result_detailed()` recebe `actor=` e chama `record_editorial_action()`
- [x] `ai_batch_prompt_template.txt` atualizado com todos os campos da Fase 4 (gravidade, risco_investigativo, polemica, confiabilidade, titulo_sugerido, subtitulo_sugerido, tags + scoring criteria)
- [x] `pages/2_Lotes_IA.py` usa `validate_ai_response()` — feedback de erros de campos
- [x] Log de importação mostra justificativa_score por artigo
- [x] `tests/test_phase4_ai.py` — 37 testes (item, response, import, constantes)

### Arquivos Criados/Modificados
```
prompts/ai_batch_prompt_template.txt  (todos os campos do prompt — reescrito)
src/news_radar/ai_batches.py          (validate_ai_item, validate_ai_response, actor em import)
pages/2_Lotes_IA.py                   (validate_ai_response, st.code, métricas, reimport)
tests/test_phase4_ai.py               (novo — 37 testes)
```

### Critérios de Aceite
- [x] Prompt copiado com 1 clique (st.code com botão nativo)
- [x] Métricas de lote visíveis (tokens, palavras)
- [x] Reimportação de lote concluído possível
- [x] JSON inválido mostra erro amigável e não importa nada
- [x] ID fora do lote exibe aviso e bloqueia importação < 40%
- [x] Campos fora do range 0-10 reportados como item_errors
- [x] Prioridade inválida reportada como item_error
- [x] Importação registra ação editorial em editorial_actions
- [x] 105 testes passando, 2 skipped

---

## Fase 5 — Deduplicação e Agrupamento por Assunto ✅ Concluída

**Objetivo:** Agrupar notícias sobre o mesmo evento em clusters persistidos.

**Concluída em:** 2026-05-29

### Tarefas
- [x] Criar tabelas `story_clusters` e `cluster_articles` em db.py (idempotentes)
- [x] Criar `src/news_radar/clusters.py` com algoritmo 3 fases:
  1. Agrupamento por `title_signature` exato (maior confiança)
  2. Agrupamento por entidades comuns do `ai_json` (confiança média)
  3. Agrupamento por keywords do título (menor confiança)
- [x] `cluster_score = avg(final_score_brasil) × log2(source_count + 1)`
- [x] IDs de cluster determinísticos (mesmo label+scope+tipo → mesmo ID)
- [x] Persistência idempotente via `INSERT ... ON CONFLICT DO UPDATE`
- [x] Funções: `cluster_articles_to_db`, `list_db_clusters`, `get_db_cluster_articles`, `set_primary_article`, `archive_cluster`, `cluster_stats`
- [x] CLI: `python -m news_radar.cli cluster-articles --hours 72 --scope brasil`
- [x] `pages/4_Clusters.py`: duas abas — banco (persistido) + em tempo real (in-memory)
- [x] Ações na dashboard: arquivar cluster, definir artigo primário
- [x] `tests/test_phase5_clusters.py` — 35 testes

### Arquivos Criados/Modificados
```
src/news_radar/db.py               (story_clusters + cluster_articles + 4 índices)
src/news_radar/clusters.py         (novo — módulo completo de clustering)
src/news_radar/cli.py              (comando cluster-articles)
pages/4_Clusters.py                (duas abas: banco + tempo real)
tests/test_phase5_clusters.py      (novo — 35 testes)
```

### Critérios de Aceite
- [x] Tabelas criadas com `CREATE TABLE IF NOT EXISTS` (idempotentes)
- [x] Artigos com mesma `title_signature` agrupados
- [x] Artigos sem cluster não são afetados
- [x] Cluster pode ser recalculado sem apagar artigos
- [x] Dashboard mostra clusters com contagem de fontes e score
- [x] Editor pode marcar artigo primário e arquivar cluster
- [x] 138 testes passando, 2 skipped
- [x] Coleta, ranking, IA, Telegram, scheduler e cards continuam compatíveis

---

## Fase 6 — Ranking Editorial Avançado ✅ Concluída

**Objetivo:** Ranking explicável para artigos e clusters, integração de score_explainer.

**Concluída em:** 2026-05-29

### Tarefas
- [x] Criar `src/news_radar/ranking.py` com:
  - `explain_cluster_score(cluster, articles)` — explicação estruturada
  - `rank_clusters_by_dimension(clusters, articles_by_cluster, dimension)` — reordenação
  - `score_summary(article, scope)` — resumo compacto com top dimensões IA
  - `_extract_ai_dimension()`, `_avg_ai_dimensions()` — helpers
  - `RANKING_DIMENSIONS`, `DEFAULT_WEIGHTS`, `DIMENSION_ICONS` — constantes
- [x] `pages/4_Clusters.py`: seletor de dimensão de ranking + barras de dimensões IA + explain_cluster_score
- [x] `pages/3_Ranking.py`: `show_explanation=True` por padrão + seletor de dimensão IA + top dimensões na coluna lateral
- [x] `tests/test_phase6_ranking.py` — 34 testes (extract, avg, explain, rank, summary, score, formula)

### Arquivos Criados/Modificados
```
src/news_radar/ranking.py        (novo — módulo de ranking explicável)
pages/4_Clusters.py              (seletor de dimensão, explain_cluster_score, barras IA)
pages/3_Ranking.py               (show_explanation padrão True, seletor de dimensão, score_summary)
tests/test_phase6_ranking.py     (novo — 34 testes)
```

### Critérios de Aceite
- [x] score_explainer.py integrado e visível por padrão na página de Ranking
- [x] Clusters ranqueados por múltiplas dimensões (score, fontes, risco, dinheiro, etc.)
- [x] explain_cluster_score() gera sinais e explicação em linguagem natural
- [x] score_summary() fornece resumo compacto para artigos
- [x] 172 testes passando, 2 skipped
- [x] Coleta, IA, clustering, Telegram continuam compatíveis

### Notas (decisões de escopo)
- `score_weights` (tabela DB): reservado para Fase 7 — pesos em `DEFAULT_WEIGHTS` em Python por ora
- `editor_score_override`: campo futuro — não implementado nesta fase
- Histórico de scores: Fase 8

---

## Fase 7 — Geração de Cards via HTML/PNG ✅ Concluída

**Objetivo:** Preview de card no dashboard, templates versionados, melhor experiência.

**Concluída em:** 2026-05-29

### Tarefas
- [x] `build_card_context()` — extrai todos os dados do artigo (título, subtítulo, score, tags, etc.)
- [x] `render_card_html()` — renderiza HTML sem Playwright (novo)
- [x] `save_card_html()` — salva HTML em `data/cards/` para auditoria (novo)
- [x] `is_playwright_available()` — verifica se Playwright está instalado (novo)
- [x] `list_templates()` — lista templates disponíveis (novo)
- [x] `render_cards()` — atualizado: salva HTML antes de PNG, fallback se Playwright ausente
- [x] `_render_html()` — atualizado: suporta novos placeholders `subtitulo_html`, `categoria_tag`, `pontos_html`
- [x] `card-editorial-base.html` totalmente suportado pelo renderer (novos placeholders adicionados)
- [x] Migration `card_html_path TEXT` em `articles` (db.py MIGRATION_SQL)
- [x] `update_card_status()` aceita `html_path` opcional (repository.py)
- [x] Dashboard `5_Editorial.py`: view "Gerar Card" com seleção de artigo/cluster, edição título/subtítulo, preview HTML, geração PNG
- [x] `record_editorial_action(action="card_generated")` registrado na ação de geração
- [x] `tests/test_phase7_cards.py` — 47 testes (build_card_context, render, save, list_templates, validação)
- [x] Preview HTML via `st.components.v1.html()` na dashboard
- [x] Dashboard não quebra se Playwright ausente (fallback HTML com aviso)
- [ ] PNG com Playwright (pendente: verificar instalação no Docker — ver Fase 8)

### Notas de escopo (decisões)
- Jinja2: não migrado — substituição `str.replace()` permanece (compatível, sem dependência nova)
- `card_templates` DB table: não implementada — templates listados do filesystem (`list_templates()`)
- Playwright: integrado no fluxo com fallback HTML. Docker pode exigir `playwright install-deps` adicional.

### Arquivos Criados/Modificados
```
src/news_radar/card_renderer.py   (reescrito — 7 funções novas/atualizadas)
src/news_radar/db.py              (migration card_html_path)
src/news_radar/repository.py      (update_card_status: html_path opcional)
pages/5_Editorial.py              (view "Gerar Card" adicionada)
tests/test_phase7_cards.py        (novo — 47 testes)
```

### Critérios de Aceite
- [x] Editor consegue selecionar artigo ou cluster
- [x] Sistema sugere título/subtítulo usando ai_json quando existir
- [x] Sistema permite preview do card (HTML via components.v1.html)
- [x] Nenhum placeholder cru aparece no HTML final (testado em 47 casos)
- [x] Card HTML é salvo em data/cards/
- [x] PNG é gerado se Playwright estiver disponível
- [x] Ação editorial é registrada (card_generated)
- [x] Dashboard não quebra sem Playwright (aviso + HTML-only mode)
- [x] 219 testes passando, 2 skipped
- [x] tasks.md atualizado

---

## Fase 8 — Aprovação, Publicação e Auditoria ✅ Concluída

**Objetivo:** Histórico completo de ações, rastreabilidade total, comentários do revisor.

**Concluída em:** 2026-05-29

### Tarefas
- [x] `_try_update_article_editorial_status()` — helper best-effort para atualizar articles
- [x] `approve_article()` — agora escreve `articles.editorial_status='approved'` (gap da spec corrigido)
- [x] Todas as funções (approve_article, reject_article, approve_card, reject_card, mark_published) aceitam `notes` opcional
- [x] `notes` persiste em `dispatches.review_notes` e em `editorial_actions.notes`
- [x] `mark_published()` aceita `user` e `notes`, registra `editorial_action("published")`
- [x] Migration `review_notes TEXT` em `dispatches` (db.py)
- [x] `dashboard_queries.py`: `article_audit_history()`, `dispatch_audit_history()`, `audit_page_actions()`, `audit_metrics()`
- [x] `pages/11_Auditoria.py`: página de auditoria com filtros (período, tipo de ação, ator), métricas e busca por artigo
- [x] `pages/0_Edicoes.py`: campo de nota do revisor por dispatch + expander de histórico de ações
- [x] `tests/test_phase8_approval.py`: 29 testes (approve, reject, publish, idempotência, notas, auditoria)
- [x] `tests/test_phase3_integration.py`: atualizado para nova assinatura de `_try_record_editorial_action`

### Arquivos Criados/Modificados
```
src/news_radar/dispatch.py         (helpers e funções com notes, mark_published auditável)
src/news_radar/db.py               (migration review_notes)
src/news_radar/dashboard_queries.py (4 funções de auditoria novas)
pages/0_Edicoes.py                 (campo notes + histórico por dispatch)
pages/11_Auditoria.py              (nova — página de auditoria editorial)
tests/test_phase8_approval.py      (novo — 29 testes)
tests/test_phase3_integration.py   (ajuste de assinatura)
```

### Critérios de Aceite
- [x] Toda aprovação/rejeição registrada com ator e timestamp
- [x] Histórico de ações visível por artigo (dashboard + query)
- [x] Editor pode adicionar nota ao revisar (campo no 0_Edicoes.py)
- [x] Página de auditoria com filtros funcionais (11_Auditoria.py)
- [x] articles.editorial_status='approved' escrito por approve_article() (gap corrigido)
- [x] mark_published() registra ação editorial auditável
- [x] 248 testes passando, 2 skipped

### Notas (decisões de escopo)
- Alerta para dispatches sem ação há mais de 2h: reservado para Fase 9
- Limpeza automática de editorial_actions (>90 dias): reservado para Fase 9

---

## Fase 9 — Hardening, Robustez e Acabamento Operacional ✅ Concluída

**Objetivo:** Hardening, robustez e documentação operacional. Sem grandes features novas.

**Concluída em:** 2026-05-29

### Tarefas
- [x] `Dockerfile`: Playwright Chromium instalado via `playwright install chromium --with-deps` (bundled, confiável)
- [x] `card_renderer._chromium_executable()`: detecta executável via env vars e PATH (Docker + dev local)
- [x] `db.py`: migrations versionadas em dict com chaves únicas (`MIGRATION_SQL: dict[str, str]`)
- [x] `db.py`: `schema_migrations` table — init_db() aplica apenas migrations pendentes
- [x] `db.py`: `_ensure_datetime_columns()` com guard — só executa ALTER se coluna não for TIMESTAMPTZ
- [x] `cli.py`: comando `backup` via pg_dump (com fallback amigável se pg_dump ausente)
- [x] `dashboard_queries.py`: `@_ttl_cache` decorator para queries pesadas (source_health, pipeline_health, ai_coverage_stats, top_entities, compute_alerts)
- [x] `docs/OPERATIONS.md`: guia operacional completo
- [x] `docs/DEPLOYMENT.md`: passo a passo de deploy local e produção com Docker
- [x] `docs/checklist-e2e.md`: checklist de validação end-to-end com 12 seções
- [x] `CLAUDE.md`: documentação completa do codebase para sessões futuras de IA
- [x] `tests/test_phase9_hardening.py`: 22 testes (migrations, Chromium, TTL cache, backup, CLI parser)

### Arquivos Criados/Modificados
```
Dockerfile                        (playwright install --with-deps, sem SKIP_DOWNLOAD)
src/news_radar/card_renderer.py   (_chromium_executable() + executable_path no launch)
src/news_radar/db.py              (migrations dict, schema_migrations table, guard ALTER)
src/news_radar/cli.py             (comando backup)
src/news_radar/dashboard_queries.py (@_ttl_cache + 5 funções pesadas cacheadas)
docs/OPERATIONS.md                (novo — guia operacional)
docs/DEPLOYMENT.md                (novo — guia de deploy)
docs/checklist-e2e.md             (novo — checklist E2E com 12 seções)
CLAUDE.md                         (novo — documentação do codebase)
tests/test_phase9_hardening.py    (novo — 22 testes)
```

### Critérios de Aceite
- [x] Dockerfile build instala Playwright corretamente
- [x] PNG gerado no container (se build com acesso à internet)
- [x] init_db() idempotente — aplica só migrations pendentes
- [x] _ensure_datetime_columns não executa ALTER em colunas já TIMESTAMPTZ
- [x] Fluxo E2E validável pelo checklist em docs/checklist-e2e.md
- [x] Testes passam (279 passed, 2 skipped)
- [x] tasks.md atualizado

### Notas (fora do escopo desta fase)
- Pool de conexões PostgreSQL: requer configuração de servidor e benchmark real
- Paginação em queries > 10k artigos: implementar quando necessário com dados reais
- Separação db.py em múltiplos módulos: refatoração maior, reservada para versão futura

---

## Fase 10.1 — Base de Dados e Scraping de Portais ✅ Concluída

**Objetivo:** Arquitetura observável e controlada para scraping de portais brasileiros, piauienses e teresinenses, coexistindo com o pipeline RSS atual.

**Concluída em:** 2026-05-29

### Tarefas
- [x] `trafilatura>=1.12,<2.0` adicionado ao `requirements.txt`
- [x] Migrations versionadas: `source_rules`, `scrape_runs`, `scraped_pages` (`db.py` — 10 entradas v10_*)
- [x] Pacote `src/news_radar/scraper/` criado com 8 módulos:
  - `__init__.py` — exports públicos
  - `models.py` — FetchResult, ExtractionResult, ScrapeRunStats
  - `fetcher.py` — download com timeout/retry/user-agent
  - `extractors.py` — trafilatura, css_selectors, playwright
  - `strategies.py` — wrappers de estratégia
  - `registry.py` — mapeamento strategy → executor
  - `rules.py` — CRUD de source_rules
  - `runs.py` — CRUD de scrape_runs/scraped_pages
  - `jobs.py` — run_extraction_test, run_source_scrape
- [x] `config/portal_sources_seed.yaml` — 34 portais seedados (14 nacionais, 13 PI/THE, 7 oficiais locais, + nacionais oficiais)
- [x] `scripts/seed_portal_sources.py` — seed idempotente com --dry-run
- [x] CLI: `test-extraction --url --strategy --timeout`
- [x] CLI: `scrape-source --source-id|--source-name --urls --dry-run --max-items`
- [x] `dashboard_queries.py`: scraping_overview, scraping_recent_runs, scraping_source_rules
- [x] `pages/12_Scraping.py` — 5 abas: Visão Geral, Regras de Fonte, Execuções, Testar URL, Portais Candidatos
- [x] `tests/test_phase10_scraping.py` — 30 testes (migrations, seed, fetcher, extractor, registry, jobs, dashboard, CLI, compat)
- [x] `docs/OPERATIONS.md` — seção de scraping adicionada
- [x] `tasks.md` atualizado

### Arquivos Criados/Modificados
```
requirements.txt                         (trafilatura adicionado)
src/news_radar/db.py                     (10 entradas v10_* em MIGRATION_SQL)
src/news_radar/scraper/__init__.py       (novo)
src/news_radar/scraper/models.py         (novo)
src/news_radar/scraper/fetcher.py        (novo)
src/news_radar/scraper/extractors.py     (novo)
src/news_radar/scraper/strategies.py     (novo)
src/news_radar/scraper/registry.py       (novo)
src/news_radar/scraper/rules.py          (novo)
src/news_radar/scraper/runs.py           (novo)
src/news_radar/scraper/jobs.py           (novo)
src/news_radar/cli.py                    (2 comandos: test-extraction, scrape-source)
src/news_radar/dashboard_queries.py     (3 funções de scraping)
config/portal_sources_seed.yaml          (novo — 34 portais)
scripts/seed_portal_sources.py           (novo — seed idempotente)
pages/12_Scraping.py                     (novo — 5 abas)
tests/test_phase10_scraping.py           (novo — 30 testes)
docs/OPERATIONS.md                       (seção scraping adicionada)
```

### Critérios de Aceite
- [x] Banco possui tabelas source_rules, scrape_runs, scraped_pages
- [x] Seed de portais existe e é idempotente
- [x] Portais candidatos aparecem na dashboard (aba "Portais Candidatos")
- [x] É possível testar uma URL pela dashboard (aba "Testar URL")
- [x] É possível rodar test-extraction via CLI
- [x] scrape_runs registra sucesso/erro
- [x] RSS atual continua funcionando (collector.py não alterado)
- [x] Docker continua subindo (migrations são aditivas)
- [x] Testes passam (30 novos + todos os anteriores)
- [x] tasks.md atualizado
- [x] docs/OPERATIONS.md atualizado

### Como usar
```bash
# Aplicar migrations
python -m news_radar.cli init-db

# Popular portais candidatos (enabled=False)
python scripts/seed_portal_sources.py
python scripts/seed_portal_sources.py --dry-run  # simula sem alterar

# Testar extração de URL
python -m news_radar.cli test-extraction --url "https://g1.globo.com/pi/" --strategy trafilatura

# Scraping com dry-run (não insere artigos)
python -m news_radar.cli scrape-source --source-name "G1 Piauí" --urls "https://g1.globo.com/pi/noticia1/" --dry-run
```

### Notas (fora do escopo desta fase)
- Ativação real de fontes de scraping: validar cada portal individualmente antes de enabled=true
- Integração de scraped_pages → articles (pipeline de ingestão scraping): Fase 10.2
- Sitemap/news-sitemap strategy: Fase 10.3
- Scrapy: não implementado intencionalmente — arquitetura preparada para adição futura

---

## Fase 10.2 — Ingestão: scraped_pages → articles ✅ Concluída

**Objetivo:** Integrar scraped_pages ao pipeline principal articles, permitindo que notícias
coletadas por scraping sejam normalizadas, inseridas no banco, ranqueadas e apareçam
na dashboard como qualquer notícia RSS.

**Concluída em:** 2026-05-30

### Tarefas
- [x] Migrations versionadas v10.2 em `db.py` — 7 entradas novas em `MIGRATION_SQL`:
  - `scraped_pages.content_text TEXT` — armazena texto extraído para ingestão
  - `scraped_pages.ingestion_status TEXT DEFAULT 'pending'`
  - `scraped_pages.article_id TEXT REFERENCES articles(id) ON DELETE SET NULL`
  - `scraped_pages.ingestion_error TEXT`
  - `scraped_pages.ingested_at TIMESTAMPTZ`
  - Índices em `ingestion_status` e `article_id`
- [x] `src/news_radar/scraper/ingestion.py` — módulo de ingestão com:
  - `build_article_from_scraped_page(page, source=None)` — transforma page → article dict
  - `get_eligible_pages(source_id, run_id, limit)` — query de páginas elegíveis
  - `count_eligible_pages(source_id, run_id)` — contagem rápida
  - `mark_scraped_page_ingested(page_id, article_id)` — marca como ingested
  - `mark_scraped_page_ingestion_error(page_id, error_message)` — marca como erro
  - `ingest_scraped_pages(source_id, run_id, limit, dry_run)` — função principal
- [x] `src/news_radar/scraper/runs.py` — `insert_scraped_page` aceita `content_text` (backward-compatible)
- [x] `src/news_radar/scraper/__init__.py` — exporta todas as funções de ingestion
- [x] `src/news_radar/cli.py` — comando `ingest-scraping` com --source-id, --source-name, --run-id, --limit, --dry-run
- [x] `src/news_radar/dashboard_queries.py` — `ingestion_overview()` e `ingestion_recent_results()`
- [x] `pages/12_Scraping.py` — nova aba "🔄 Ingestão → Articles" com métricas, dry-run, botão, histórico e link pós-ranking
- [x] `tests/test_phase10_2_ingestion.py` — 36 testes (migrations, build, dry-run, erros, CLI, queries, compat)
- [x] `tasks.md` atualizado

### Arquivos Criados/Modificados
```
src/news_radar/db.py                        (7 entradas v10_2_* em MIGRATION_SQL)
src/news_radar/scraper/ingestion.py         (novo — módulo de ingestão)
src/news_radar/scraper/runs.py              (insert_scraped_page: +content_text)
src/news_radar/scraper/__init__.py          (exports de ingestion)
src/news_radar/cli.py                       (cmd_ingest_scraping + parser)
src/news_radar/dashboard_queries.py        (ingestion_overview, ingestion_recent_results)
pages/12_Scraping.py                        (nova aba Ingestão + import run_cli corrigido)
tests/test_phase10_2_ingestion.py           (novo — 36 testes)
```

### Critérios de Aceite
- [x] Existe `src/news_radar/scraper/ingestion.py`
- [x] Existe comando `ingest-scraping` no CLI
- [x] scraped_pages bem-sucedidas podem virar articles
- [x] dry-run funciona (simula sem persistir)
- [x] Duplicatas por canonical_url são evitadas (reutiliza upsert_article)
- [x] Páginas ingeridas ficam marcadas (ingestion_status='ingested')
- [x] Erros ficam registrados (ingestion_status='error', ingestion_error)
- [x] Erro em uma página não derruba o lote inteiro
- [x] Dashboard permite acompanhar/acionar ingestão (aba 4)
- [x] RSS atual continua funcionando (collector.py não alterado)
- [x] Ranking continua funcionando (ranker.py não alterado)
- [x] Testes passam (36 novos + todos os anteriores)
- [x] tasks.md atualizado

### Como usar
```bash
# Aplicar migrations
python -m news_radar.cli init-db

# Dry-run: simula sem persistir
python -m news_radar.cli ingest-scraping --limit 20 --dry-run

# Ingestão real
python -m news_radar.cli ingest-scraping --limit 50

# Por fonte específica
python -m news_radar.cli ingest-scraping --source-name "G1 Piauí" --limit 10

# Por run_id específico
python -m news_radar.cli ingest-scraping --run-id 123

# Após ingestão: recalcular ranking
python -m news_radar.cli rank
```

### Como validar no banco
```sql
-- Páginas ingeridas
SELECT ingestion_status, COUNT(*) FROM scraped_pages GROUP BY ingestion_status;

-- Artigos originados do scraping
SELECT * FROM articles WHERE raw_json::jsonb->>'origin' = 'scraping' LIMIT 10;

-- Histórico por página
SELECT sp.url, sp.ingestion_status, sp.ingested_at, a.title AS article_title
FROM scraped_pages sp
LEFT JOIN articles a ON sp.article_id = a.id
WHERE sp.ingestion_status = 'ingested'
ORDER BY sp.ingested_at DESC;
```

### Notas (fora do escopo desta fase)
- Ativação de portais individuais: validar cada um em "Testar URL" antes de enabled=true
- Integração content_text nos portais codificados: dashboard 12 ainda salva sem content_text
  (portais devem passar content_text ao chamar insert_scraped_page na próxima fase)
- Sitemap/news-sitemap como estratégia: Fase 10.3
- Scrapy: não necessário com a arquitetura atual
