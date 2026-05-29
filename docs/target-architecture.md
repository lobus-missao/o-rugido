# Arquitetura Alvo — News Radar RSS

> Documento de arquitetura desejada, derivado da análise do projeto existente.
> Evolução incremental — sem reescritas destrutivas.

---

## 1. Fluxo Ideal

```
Fontes Externas
  ├── RSS (feedparser)             → 57+ feeds configurados em sources DB
  ├── APIs públicas/gratuitas      → Google News RSS, Agência Brasil, etc.
  ├── Scraping simples             → requests + trafilatura (quando RSS não existe)
  ├── Scraping com browser         → Playwright (quando JS necessário)
  └── Importação manual            → CSV / JSON direto na dashboard
         ↓
  [Ingestão]
  collector.py + novos adapters
  Salva raw_json, canonical_url, title_signature
  Registra em feed_runs (log)
         ↓
  [Normalização]
  strip_html, canonicalize_url, padronizar data, extrair summary
  Preenche: title, url, source, source_scope, source_trust, published_at
         ↓
  [Deduplicação]
  1º: canonical_url exato (atual — funciona)
  2º: title_signature fuzzy (atual — funciona)
  3º: similaridade textual TF-IDF (futuro — Fase 5)
         ↓
  [Agrupamento por Assunto / Clustering]
  story_clusters + cluster_articles (Fase 5)
  Agrupa notícias do mesmo evento
  Score do cluster = agregado dos artigos
         ↓
  [Classificação Editorial]
  Automática: keyword scoring (ranker.py — funciona)
  Com IA: campos retornados pela IA (editoria, categoria, localidade, entidades)
         ↓
  [Ranking Inteligente]
  auto_score = keyword dimensions × pesos
  ai_score = média de dimensões IA × 10
  final_score = auto × 0.58 + ai × 0.42
  Score configurável: pesos editáveis na dashboard (Fase 6)
         ↓
  [IA Assistida]
  Seleção de lote → geração de prompt
  Cópia manual → ChatGPT/Claude externo
  Importação JSON → validação → atualização de scores
  (sem chamada direta a API paga nesta fase)
         ↓
  [Dashboard Editorial]
  Cockpit central: Streamlit multipage
  Filtros, tabelas, ações, detalhes
  Controle de todos os estados editoriais
         ↓
  [Geração de Card via Template HTML]
  Seleciona notícia/cluster
  Preenche template Jinja2/HTML
  Playwright screenshot → PNG
  Preview antes da aprovação
         ↓
  [Aprovação]
  Via dashboard (primário) ou Telegram (notificação)
  Registro de quem aprovou, quando, observação
         ↓
  [Publicação / Notificação]
  Marcação manual no dashboard
  Notificação opcional via Telegram
  Integração opcional via webhook/n8n
```

---

## 2. Papel de Cada Componente

### 2.1 Banco de Dados (PostgreSQL)
**É a fonte de verdade do sistema.**

- Contém todos os artigos, scores, estados editoriais, logs
- Nenhuma regra de negócio vive no n8n, Telegram ou arquivos externos
- Migrations incrementais — nunca destrutivas
- JSONB para dados flexíveis (ai_json, entities_json, raw_json)
- Índices em: canonical_url, title_signature, published_at, editorial_status, final_scores, source_scope

### 2.2 Python Backend (`src/news_radar/`)
**Contém 100% da regra de negócio.**

- `collector.py` — ingestão RSS e futuros adapters
- `ranker.py` — fórmulas de score
- `ai_batches.py` — geração de prompt e importação de IA
- `card_renderer.py` — geração de card
- `dispatch.py` — fluxo editorial e aprovação
- Novos módulos: `sources.py`, `clusters.py`, `audit.py`, `scheduler.py`

### 2.3 CLI (`cli.py`)
**Interface de linha de comando para todas as operações.**

- Cada comando é atômico e retorna JSON
- Usado pela API Flask e por scripts de manutenção
- Não deve conter regra de negócio — apenas chama módulos

### 2.4 API Flask (`api_server.py`)
**Bridge HTTP para integração externa.**

- n8n chama a API; a API chama o CLI/Python
- Sem lógica de negócio na API
- Endpoints: /pipeline/collect, /pipeline/rank, /api/dispatch/run, /api/review/*, /api/cards/*
- Futuramente: endpoints para scheduler interno, audit, sources CRUD

### 2.5 Dashboard Streamlit
**Cockpit editorial central.**

O dashboard deve ser o ponto de controle de TUDO:

```
Visão Geral      → métricas, alertas, cobertura IA
Fontes           → CRUD de fontes RSS, status de cada fonte
Coletas/Jobs     → log de coletas, retry, saúde do pipeline
Notícias         → tabela completa com filtros, search, ações
Clusters         → assuntos agrupados, score agregado
Ranking          → top N por escopo, filtros avançados
IA Assistida     → geração de lote, prompt, importação JSON
Mesa Editorial   → fila de aprovação, ações em lote
Cards/Templates  → geração, preview, aprovação
Aprovação        → histórico de aprovações/rejeições
Auditoria        → logs de todas as ações, rastreabilidade
Configurações    → pesos do ranking, parâmetros do sistema
```

### 2.6 n8n (Camada Auxiliar)
**NÃO é o cérebro. Não contém regra de negócio.**

Pode continuar fazendo:
- Agendamento de coleta (trigger HTTP)
- Agendamento de dispatch (trigger HTTP)
- Webhook de callbacks do Telegram
- Notificações externas
- Automações simples sem decisão

Não deve fazer:
- Selecionar quais notícias publicar
- Calcular scores
- Gerenciar estados editoriais
- Importar resultados de IA
- Controlar aprovações

**Plano de substituição gradual:**
- Fase 1: Adicionar APScheduler interno (coleta e dispatch sem n8n)
- Fase 1: Manter n8n como opção alternativa por compatibilidade
- Futuro: n8n vira opcional para automações extras

### 2.7 Telegram
**Canal de notificação e aprovação rápida.**

- Recebe artigos para aprovação editorial
- Botões inline para aprovar/rejeitar artigo e card
- Callbacks processados pelo poller ou webhook
- Estado persistido 100% no PostgreSQL
- Dashboard é a fonte de verdade — Telegram é notificação

### 2.8 IA (Camada Assistida)
**Assistente, não fonte factual.**

- Não chama API de IA diretamente (sem custo automático)
- Fluxo: sistema gera prompt estruturado → usuário processa externamente → cola JSON
- IA classifica, prioriza, sugere títulos/resumos
- Importação validada contra schema esperado
- Rollback possível em caso de erro
- IA não decide publicação — editor decide

### 2.9 Motor de Templates
**Geração de card editorial.**

- Template HTML versionado (`templates/card.html` e futuros)
- Variáveis preenchidas por `card_renderer.py`
- Playwright renderiza para PNG
- Preview antes de aprovar
- Template pode ser modificado sem alterar código Python

---

## 3. Fronteiras Entre Módulos

```
┌─────────────────────────────────────────────────────────────┐
│                    DASHBOARD (Streamlit)                     │
│  Cockpit editorial — controla estados — aciona ações         │
└──────────────────────────┬──────────────────────────────────┘
                           │ direct import
┌──────────────────────────▼──────────────────────────────────┐
│              PYTHON BACKEND (src/news_radar/)                │
│  Toda regra de negócio: coleta, rank, IA, card, dispatch     │
└──────┬───────────────────┬────────────────────┬────────────┘
       │ SQL              │ SQL                │ SQL
┌──────▼──────┐    ┌──────▼──────┐    ┌───────▼──────┐
│ PostgreSQL  │    │  data/files │    │  templates/  │
│ (verdade)   │    │ prompts/PNG │    │  card.html   │
└─────────────┘    └─────────────┘    └──────────────┘
       ↑                                     ↑
┌──────┴──────┐                      ┌───────┴──────┐
│  Flask API  │◄── n8n (HTTP) ──────►│  Playwright  │
│  port 8888  │                      │  (screenshot)│
└─────────────┘                      └──────────────┘
       ↑
┌──────┴──────┐
│  Telegram   │◄── poller/webhook
│  Bot API    │
└─────────────┘
```

**Regras de fronteira:**
1. Dashboard importa Python diretamente — não chama API Flask
2. n8n só chama a API Flask — nunca conecta ao banco diretamente
3. Telegram não tem lógica de negócio — só recebe notificações e envia callbacks
4. IA não tem acesso ao banco — opera apenas em JSON fornecido pelo sistema
5. Playwright é usado apenas em `card_renderer.py`

---

## 4. Modelo de Dados Alvo

### Tabelas existentes (preservar):
- `articles` — central, adicionar colunas incrementalmente
- `feed_runs` — preservar como está
- `ai_batches` — preservar como está
- `dispatches` — preservar como está

### Tabelas a adicionar (incrementalmente):
```
sources              → CRUD de fontes (substitui feeds.yaml parcialmente)
story_clusters       → agrupamentos de notícias por assunto
cluster_articles     → relação M:N artigos-clusters
editorial_actions    → histórico de ações editoriais (auditoria)
card_templates       → templates versionados
score_weights        → pesos configuráveis do ranking
```

---

## 5. Como Escalar Futuramente

**Curto prazo (sem reescrever):**
- APScheduler para eliminar n8n como dependência crítica
- Tabela `sources` para CRUD de feeds via dashboard
- Auditoria básica de ações

**Médio prazo:**
- Clustering com TF-IDF ou simhash
- Score configurável pela dashboard
- Templates de card versionados

**Longo prazo (se necessário):**
- Migrar de Streamlit para React/Next.js (se dashboard crescer muito)
- Workers assíncronos (Celery/RQ) para coleta paralela
- API REST completa substituindo CLI-via-subprocess
- Chamadas diretas a API de IA (Claude, GPT) com controle de custo
