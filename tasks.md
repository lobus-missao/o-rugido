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

## Fase 6 — Ranking Editorial Avançado

**Objetivo:** Ranking configurável pela dashboard, score manual do editor.

### Tarefas
- [ ] UI em Configurações para ajustar pesos por dimensão e escopo
- [ ] Salvar pesos em tabela `score_weights`
- [ ] `ranker.py`: ler pesos da tabela (com fallback para pesos hardcoded)
- [ ] Campo `editor_score_override` em artigos
- [ ] Dashboard: campo para editor ajustar score manualmente
- [ ] Histórico de alterações de score

### Riscos
- Pesos errados podem desordenar todo o ranking
- Necessário UI de rollback de pesos

### Arquivos Prováveis
```
src/news_radar/ranker.py     (ler pesos da tabela)
src/news_radar/db.py         (tabela score_weights)
pages/3_Ranking.py           (UI de pesos)
```

### Critérios de Aceite
- [ ] Editor ajusta pesos pelo dashboard sem alterar código
- [ ] Ranking reflete pesos imediatamente após recalculo
- [ ] Score manual do editor override o automático
- [ ] Histórico de scores por artigo

---

## Fase 7 — Geração de Cards via HTML/PNG

**Objetivo:** Preview de card no dashboard, templates versionados, melhor experiência.

### Tarefas
- [ ] Preview de card antes de aprovar (`st.image()` do PNG)
- [ ] Verificação de instalação do Playwright na dashboard
- [ ] Suporte a múltiplos templates (`card_templates` tabela)
- [ ] Migrar `_render_html()` para Jinja2
- [ ] `card-editorial-base.html` como alternativa ao `card.html` atual
- [ ] Geração de card direto da mesa editorial

### Riscos
- Migração para Jinja2 não deve quebrar cards existentes (manter compatibilidade de placeholders)
- Playwright pode falhar em alguns ambientes

### Arquivos Prováveis
```
src/news_radar/card_renderer.py  (Jinja2, multi-template)
templates/card.html              (manter como está)
templates/card-editorial-base.html (novo)
src/news_radar/db.py             (tabela card_templates)
pages/5_Editorial.py             (gerar card direto)
```

### Critérios de Aceite
- [ ] Preview de card visível antes de aprovar
- [ ] Múltiplos templates disponíveis
- [ ] Playwright ausente não crash dashboard
- [ ] Jinja2 compatível com placeholders existentes

---

## Fase 8 — Aprovação, Publicação e Auditoria

**Objetivo:** Histórico completo de ações, rastreabilidade total, comentários do revisor.

### Tarefas
- [ ] Implementar registro completo em `editorial_actions`
- [ ] Dashboard: histórico de ações por artigo
- [ ] Campo `review_notes` no dispatch
- [ ] UI para editor adicionar comentário ao aprovar/rejeitar
- [ ] Página de Auditoria com filtros
- [ ] Alerta para dispatches sem ação há mais de 2h

### Riscos
- Tabela `editorial_actions` pode crescer rápido — adicionar limpeza automática (>90 dias)

### Arquivos Prováveis
```
src/news_radar/db.py             (tabela editorial_actions)
src/news_radar/dispatch.py       (registrar em editorial_actions)
pages/0_Edicoes.py               (review_notes)
pages/11_Auditoria.py            (nova página)
```

### Critérios de Aceite
- [ ] Toda aprovação/rejeição registrada com ator e timestamp
- [ ] Histórico de ações visível por artigo
- [ ] Editor pode adicionar nota ao revisar
- [ ] Página de auditoria com filtros funcionais

---

## Fase 9 — Refatoração e Escalabilidade

**Objetivo:** Limpeza técnica, performance, preparação para escalar.

### Tarefas
- [ ] Avaliar substituição de api_server subprocess por imports diretos
- [ ] Paginação em queries grandes (10k+ artigos)
- [ ] Pool de conexões PostgreSQL
- [ ] Cache de queries frequentes (via st.cache_data)
- [ ] Separar `db.py` em `db.py` (conexão) + `schema.py` (DDL) + `migrations.py`
- [ ] Documentar CLAUDE.md completo para o projeto
- [ ] Revisar todos os `except: pass` e adicionar logs

### Riscos
- Refatoração de api_server pode quebrar n8n se endpoints mudarem
- Pool de conexões requer configuração do PostgreSQL

### Arquivos Prováveis
```
src/news_radar/db.py             (refatorar)
api_server.py                    (remover subprocess quando possível)
dashboard.py e pages/            (st.cache_data)
CLAUDE.md                        (novo)
```

### Critérios de Aceite
- [ ] Todas as operações ≤10s com 50k artigos
- [ ] Sem subprocess desnecessário no hot path
- [ ] Todos os erros logados de forma padronizada
- [ ] CLAUDE.md completo e atualizado
