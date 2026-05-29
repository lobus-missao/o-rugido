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

## Fase 3 — Dashboard como Cockpit Editorial

**Objetivo:** Editor opera ciclo completo sem terminal ou n8n.

> **Dependência:** `8_Fontes_RSS.py` com dados reais de fontes requer Fase 2 (tabela `sources`)
> completa. As demais tarefas desta fase podem ser iniciadas antes da Fase 2 e usar fallback
> para `feeds.yaml` enquanto a tabela `sources` não existir.

### Tarefas
- [ ] `8_Fontes_RSS.py`: listar fontes com status, habilitar/desabilitar
- [ ] `5_Editorial.py`: botão "Gerar card" por artigo, botão "Marcar needs_ai"
- [ ] `0_Edicoes.py`: preview de card (`st.image()`) quando card_path existe
- [ ] `1_Operacao.py`: status do scheduler, próxima execução
- [ ] Verificar que todos os botões de ação têm feedback visual correto
- [ ] Verificar que erros são exibidos de forma descritiva
- [ ] Adicionar confirmação para ações destrutivas (rejeitar, arquivar)

### Riscos
- Streamlit tem limitações de interatividade — some state management necessário
- st.rerun() excessivo pode causar loops

### Arquivos Prováveis
```
pages/0_Edicoes.py     (preview de card)
pages/1_Operacao.py    (status scheduler)
pages/5_Editorial.py   (ações diretas)
pages/8_Fontes_RSS.py  (CRUD de fontes)
```

### Critérios de Aceite
- [ ] Editor coleta, gera lote IA, importa, aprova, vê card, publica — tudo pela dashboard
- [ ] Fontes RSS visíveis com status no dashboard
- [ ] Preview de card visível antes de publicar

---

## Fase 4 — IA Assistida com Prompt / Importação JSON

**Objetivo:** Melhorar experiência do fluxo de IA manual.

### Tarefas
- [ ] Botão de cópia do prompt (1 clique)
- [ ] Exibir métricas do lote antes de gerar (tokens, palavras, artigos)
- [ ] Permitir reimportação de lote já concluído
- [ ] Adicionar validação de schema por campo no `import_ai_result_detailed()`
- [ ] Adicionar campo `titulo_sugerido` e `subtitulo_sugerido` ao display de artigo

### Riscos
- Não quebrar fluxo de importação atual (funcional em produção)

### Arquivos Prováveis
```
pages/2_Lotes_IA.py         (UI melhorias)
src/news_radar/ai_batches.py (validação adicional)
```

### Critérios de Aceite
- [ ] Prompt copiado com 1 clique
- [ ] Métricas de lote visíveis
- [ ] Reimportação possível
- [ ] Campos sugeridos exibidos no card/artigo

---

## Fase 5 — Deduplicação e Agrupamento por Assunto

**Objetivo:** Agrupar notícias sobre o mesmo evento em clusters.

### Tarefas
- [ ] Criar tabelas `story_clusters` e `cluster_articles`
- [ ] Implementar `src/news_radar/clusters.py` com algoritmo de agrupamento
- [ ] Agrupamento por title_signature + keywords similares
- [ ] Calcular `cluster_score` agregado
- [ ] `4_Clusters.py`: listar clusters ativos, artigos por cluster
- [ ] Ações: marcar artigo primário, arquivar cluster

### Riscos
- Custo computacional de similaridade com muitos artigos
- Falsos positivos: artigos similares de assuntos distintos

### Arquivos Prováveis
```
src/news_radar/clusters.py   (novo)
src/news_radar/db.py         (novas tabelas)
pages/4_Clusters.py          (UI)
```

### Critérios de Aceite
- [ ] Artigos sobre mesmo evento agrupados automaticamente
- [ ] Cluster_score calculado e exibido
- [ ] Dashboard mostra clusters com contagem de fontes
- [ ] Editor pode marcar artigo primário

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
