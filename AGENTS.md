# AGENTS.md — News Radar RSS

Documento de regras gerais para agentes de IA colaborando neste projeto.
Leia este arquivo antes de qualquer tarefa.

---

## 1. Visão do Produto

News Radar RSS é uma plataforma editorial de monitoramento de notícias com foco em Piauí, Teresina e Brasil. Captura notícias via RSS e APIs públicas, aplica ranking automático por palavras-chave e IA assistida manual (prompt → JSON → importação), gera cards visuais PNG, e controla um fluxo editorial com aprovação.

**Objetivo central:** transformar a dashboard em cockpit editorial completo, reduzindo dependência do n8n e tornando o sistema autossuficiente sem ferramentas externas obrigatórias.

---

## 2. Stack Detectada no Projeto

| Componente | Tecnologia | Arquivo(s) principal |
|------------|------------|----------------------|
| Banco | PostgreSQL + psycopg2 (sem ORM) | `src/news_radar/db.py` |
| Backend | Python 3.14 | `src/news_radar/` |
| API HTTP | Flask 3.x porta 8888 | `api_server.py` |
| Dashboard | Streamlit 1.40 multipage | `dashboard.py` + `pages/` |
| RSS | feedparser 6.x | `src/news_radar/collector.py` |
| Card | HTML template + Playwright | `src/news_radar/card_renderer.py` |
| Scheduler | n8n (atual, a substituir) | `n8n/workflows/` |
| Telegram | Bot API (poller/webhook) | `src/news_radar/dispatch.py` |
| Config | YAML + .env | `configs/feeds.yaml`, `.env` |
| CLI | argparse | `src/news_radar/cli.py` |
| Container | Docker Compose | `docker-compose.yml` |
| HTTPS | Caddy | `Caddyfile` |
| IA local | Ollama (opcional, não usado no fluxo principal) | `src/news_radar/ai_caller.py` |

---

## 3. Papéis dos Agentes

### Product Agent
Responsável por:
- Manter a visão de produto alinhada com o objetivo editorial
- Priorizar features que reduzam trabalho manual do editor
- Garantir que a dashboard seja sempre o ponto de controle
- Recusar features que tornem o n8n obrigatório para operação

### Spec Architect
Responsável por:
- Criar e manter specs em `specs/` baseadas no projeto real
- Documentar modelos de dados com evolução incremental
- Definir fronteiras entre módulos sem destruir o que funciona
- Registrar hipóteses quando o comportamento exato for incerto

### Software Engineer
Responsável por:
- Implementar tarefas dentro do escopo de uma fase definida
- Não refatorar o que não foi pedido
- Criar migrations incrementais (nunca DROP sem consenso)
- Testar cada feature contra os critérios de aceite da spec

### Review Agent
Responsável por:
- Verificar se o código implementado corresponde à spec
- Checar se migrations são seguras (não apagam dados)
- Validar que n8n não voltou a ter regra de negócio
- Confirmar que comportamentos existentes não foram quebrados

### Refactor Agent
Responsável por:
- Propor refatorações apenas após uma feature estar estável
- Nunca refatorar sem aprovação do usuário
- Documentar o que mudou e por quê
- Não mover arquivos sem justificativa clara

---

## 4. Fluxo Obrigatório de Trabalho

```
1. Ler AGENTS.md (este arquivo)
2. Ler docs/project-audit.md
3. Ler a spec relevante em specs/
4. Ler o código existente dos arquivos afetados
5. Criar plano incremental (não reescrever tudo)
6. Implementar apenas o escopo da tarefa atual
7. Testar contra critérios de aceite da spec
8. Submeter para revisão (Review Agent ou usuário)
```

---

## 5. Restrições Absolutas

- **Não apague código funcional existente**
- **Não altere behavior existente sem instrução explícita**
- **Não faça DROP em colunas ou tabelas sem aprovação**
- **Não mova arquivos sem justificativa**
- **Não introduza dependência nova sem verificar requirements.txt**
- **Não coloque regra de negócio no n8n**
- **Não chame API de IA com custo sem consentimento explícito**
- **Não faça refatoração fora do escopo da tarefa atual**
- **Não invente arquitetura — baseie-se no projeto real**
- **Não escreva código sem ler a spec primeiro**

---

## 6. Regras para n8n

1. n8n NÃO é o cérebro do sistema. Toda regra de negócio fica no Python.
2. n8n pode chamar a API Flask — nunca o banco diretamente.
3. n8n pode ser scheduler, webhook e notificador.
4. O sistema deve funcionar SEM n8n (scheduler interno como fallback).
5. Ao adicionar features, pergunte: "isto funciona sem n8n?" Se não, revise.
6. Workflows n8n existentes não devem ser alterados nesta fase.
7. Novos workflows n8n só podem chamar endpoints da API Flask.

---

## 7. Regras para Preservar Comportamento Existente

1. O fluxo RSS → collector → ranker → banco está funcionando. Não quebre.
2. O fluxo AI batch → prompt → importação JSON está funcionando. Não quebre.
3. O fluxo dispatch → Telegram → approval está funcionando. Não quebre.
4. O fluxo card_renderer → Playwright → PNG está funcionando. Não quebre.
5. O CLI (`cli.py`) é usado pela API Flask. Cada comando deve continuar funcionando.
6. Os 9 scores existentes (`auto_score_*`, `final_score_*`, `ai_score`) devem continuar.
7. O `title_signature` e `canonical_url` são a chave de deduplicação. Não altere a lógica sem spec.

---

## 8. Regras para Testes

1. Cada critério de aceite de uma spec deve ter teste correspondente.
2. Testes estão em `tests/` — adicione arquivos `test_*.py` sem remover os existentes.
3. Testes de smoke existem em `tests/test_*.py` — não quebre.
4. Para ranking: teste a fórmula com fixtures conhecidas.
5. Para importação de IA: teste com JSON válido, JSON com IDs errados, JSON inválido.
6. Para card: teste que o arquivo PNG é gerado se Playwright disponível.
7. Use `conftest.py` para fixtures compartilhadas.

---

## 9. Regras para Dashboard

1. Dashboard é o cockpit editorial — deve ter controle de TUDO.
2. Filtros sempre no topo da página.
3. Tabela ou lista central com dados principais.
4. Painel lateral ou expander para detalhes.
5. Ações explícitas com botões nomeados (não ícones sozinhos).
6. Confirmação para ações destrutivas (rejeitar, deletar).
7. Feedback visual: spinner durante operação, success/error após.
8. Nunca colocar lógica pesada de negócio no arquivo `.py` da página — chamar módulos.
9. Evitar `st.rerun()` excessivo — usar `session_state` para estado local.
10. Cada página deve ter `set_page_config` e `sidebar_controls()`.

---

## 10. Regras para Banco de Dados

1. Migrations SEMPRE incrementais — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
2. Nunca usar `DROP COLUMN` sem aprovação explícita.
3. Preservar `raw_json` como dado bruto imutável.
4. Usar `JSONB` para dados flexíveis (ai_json, entities_json).
5. Criar índices para: URL, hash, data, status editorial, scores.
6. `editorial_status` deve ter histórico registrável (tabela futura).
7. Foreign keys com `ON DELETE CASCADE` apenas quando aprovado.
8. Todas as datas em `TIMESTAMPTZ` (já aplicado via migration existente).
9. O banco é a fonte de verdade — não usar arquivos como estado canônico.

---

## 11. Regras para Scraping

1. Usar RSS quando disponível (feedparser — padrão atual).
2. Usar requests + trafilatura para páginas sem RSS.
3. Usar Playwright apenas quando JS necessário (custo alto).
4. Sempre definir: User-Agent identificável, timeout, rate limit.
5. Respeitar robots.txt quando aplicável.
6. Não burlar paywall, login ou captcha.
7. Salvar `raw_json` / HTML bruto quando útil para debug.
8. Logar falha em `feed_runs` com status "error" e mensagem.
9. Retry máximo: 3 tentativas com backoff exponencial.

---

## 12. Regras para IA Assistida

1. Sistema gera prompt — usuário processa externamente — cola JSON.
2. Não chamar API de IA diretamente sem consentimento explícito.
3. Prompt sempre inclui escopo geográfico e regras de saída.
4. Resposta sempre JSON — validar schema antes de importar.
5. IDs do JSON devem bater com IDs do lote enviado.
6. Exibir log detalhado de importação (atualizado / ignorado / não encontrado).
7. Salvar prompt e resultado bruto em `data/ai_batches/` e `data/ai_results/`.
8. IA não é fonte factual — não confiar em IDs inventados.
9. Rollback: lote pode ser reimportado se erro for detectado.
10. Threshold mínimo de match: 40% dos IDs devem bater para habilitar importação.

---

## 13. Regras para Geração de Card HTML/PNG

1. Template HTML em `templates/` com versão no nome (futuro: `card_v2.html`).
2. Placeholders no formato `{{variavel}}` (padrão atual, compatível com `_render_html`).
3. CSS isolado no próprio template — não dependências externas de rede.
4. Dados mínimos obrigatórios: titulo, fonte, data, prioridade.
5. Playwright screenshot do elemento `#card` apenas.
6. Salvar PNG em `data/cards/card_{id[:16]}.png`.
7. Após gerar: atualizar `card_status = 'pending'` e `card_path`.
8. Preview antes de aprovar (quando possível via dashboard).
9. Regeneração segura: não altera `editorial_status` — só `card_status`.
10. Nunca bloquear o fluxo por falha no Playwright — logar e continuar.

---

## 14. Estrutura de Arquivos de Referência

```
AGENTS.md                    ← este arquivo (leia primeiro)
docs/project-audit.md        ← diagnóstico do projeto atual
docs/target-architecture.md  ← arquitetura alvo
tasks.md                     ← backlog incremental por fases
specs/00-product-vision.md   ← visão do produto
specs/01-architecture-and-boundaries.md
specs/02-data-model.md
specs/03-ingestion-sources.md
specs/04-normalization.md
specs/05-deduplication-clustering.md
specs/06-ranking-engine.md
specs/07-ai-assisted-processing.md
specs/08-editorial-dashboard.md
specs/09-card-template-renderer.md
specs/10-approval-publication.md
specs/11-audit-observability.md
specs/12-n8n-decoupling.md
specs/13-security-compliance-scraping.md
skills/python-backend-patterns.md
skills/streamlit-dashboard-patterns.md
skills/database-patterns.md
skills/ai-prompt-import-patterns.md
skills/scraping-rules.md
skills/card-rendering-patterns.md
skills/testing-review-patterns.md
prompts/01-bootstrap-existing-project.md
prompts/02-decouple-n8n.md
prompts/03-dashboard-cockpit.md
prompts/04-ai-assisted-processing.md
prompts/05-card-template-renderer.md
prompts/06-review-agent.md
templates/ai-batch-prompt-template.md
templates/card-editorial-base.html
```
