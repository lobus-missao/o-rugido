# News Radar RSS

MVP para monitorar noticias por RSS, deduplicar, salvar em PostgreSQL, ranquear por escopo editorial, enriquecer com IA opcional, revisar internamente, gerar cards PNG e preparar publicacoes aprovadas.

O Streamlit faz parte do MVP como dashboard operacional/editorial interno. Ele nao e o motor do sistema: coleta, ranking, lotes, cards e dispatch devem funcionar via CLI, API e n8n mesmo com o dashboard desligado.

## Arquitetura

**Core**

- `src/news_radar/collector.py`: coleta feeds RSS, normaliza itens e deduplica.
- `src/news_radar/db.py`: schema PostgreSQL e inicializacao idempotente.
- `src/news_radar/ranker.py`: score automatico e combinacao com score de IA.
- `src/news_radar/ai_batches.py`: gera lotes, importa retorno JSON e atualiza artigos.
- `src/news_radar/ai_caller.py`: envia lotes para IA local compativel com `/v1/chat/completions`.
- `src/news_radar/card_renderer.py`: gera cards PNG com Playwright.
- `src/news_radar/dispatch.py`: controla edicoes e fluxo de aprovacao.
- `src/news_radar/cli.py`: interface operacional principal.

**Interface operacional**

- `dashboard.py`: entrada do Streamlit multipage.
- `pages/`: operacao, rankings, lotes IA, editorial, alertas, fontes e edicoes.
- `src/news_radar/dashboard_queries.py`: consultas e acoes auxiliares do dashboard.

**Orquestracao**

- `api_server.py`: API local para o n8n acionar comandos do core.
- `n8n-workflow.json` e scripts em `scripts/`: automacoes e manutencao do n8n.
- `docker-compose.yml`: Postgres, API, Streamlit, n8n e Caddy.
- `start.ps1`: bootstrap local de desenvolvimento.

**Canal de aprovacao**

- `src/news_radar/telegram_sender.py`: envio de cards e webhook do Telegram.
- `src/news_radar/dispatch.py`: aprovar/rejeitar artigo, aprovar/regerar/rejeitar card e marcar como publicado.

**Configuracao**

- `configs/feeds.yaml`: catalogo de fontes RSS.
- `.env`: credenciais e URLs locais.
- `docker-compose.yml`: configuracao de producao/container.

## Fluxo MVP

```text
RSS
  -> collector.py
  -> PostgreSQL
  -> ranker.py
  -> lotes IA opcionais/manual ou Ollama local
  -> revisao editorial
  -> geracao de card
  -> aprovacao Telegram
  -> ready_to_publish / published no banco
```

## Instalacao local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Suba o PostgreSQL local:

```powershell
docker compose -f docker-compose.dev.yml up -d
```

Inicialize o schema consolidado:

```powershell
python -m news_radar.cli init-db
```

O `init-db` cria/atualiza `articles`, `feed_runs`, `ai_batches`, `dispatches`, `editorial_status` e indices principais sem apagar dados existentes.

## Variaveis principais

```env
DATABASE_URL=postgresql://news:senha@localhost:5432/news_radar
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NEWS_RADAR_API_URL=http://localhost:8888
```

No Docker, `OLLAMA_URL` normalmente aponta para `http://host.docker.internal:11434`.

## Comandos principais

Coletar e ranquear:

```powershell
python -m news_radar.cli collect --limit-per-feed 25
python -m news_radar.cli rank
python -m news_radar.cli show --scope piaui --limit 20
```

Gerar lotes de IA:

```powershell
python -m news_radar.cli make-ai-batches --scope piaui --top 200 --batch-size 50
python -m news_radar.cli list-ai-batches --status pending
```

Enviar um lote para Ollama local:

```powershell
python -m news_radar.cli send-ai-batch --batch-id batch_piaui_YYYYMMDD_HHMMSS_part01 --model llama3.2
```

Importar retorno JSON manual:

```powershell
python -m news_radar.cli import-ai --file data\ai_results\resultado_01.json --batch-id batch_piaui_YYYYMMDD_HHMMSS_part01
python -m news_radar.cli rank
```

Gerar card e disparar edicao:

```powershell
python -m news_radar.cli make-card --scope piaui --limit 3
python -m news_radar.cli dispatch --edition morning --scope piaui --top 3
```

Manutencao:

```powershell
python -m news_radar.cli cleanup
python -m news_radar.cli stats
```

## API local

```powershell
python api_server.py
```

Endpoints principais:

Pipeline:

- `GET /health`
- `GET /stats`
- `GET /batches?status=pending`
- `POST /pipeline/collect`
- `POST /pipeline/rank`
- `POST /pipeline/make-batches`
- `POST /pipeline/cleanup`
- `POST /cards/update-status`

Editorial:

- `GET /api/editorial/top3`
- `POST /api/dispatch/run`
- `POST /api/review/news`
- `POST /api/cards/generate`
- `POST /api/review/card`
- `GET /api/dispatch/status`
- `POST /api/telegram/callback`

## Dashboard Streamlit

```powershell
streamlit run dashboard.py
```

Paginas:

- `0_Edicoes` — status das edicoes por data e edicao
- `1_Operacao` — visao operacional geral e saude do sistema
- `2_Lotes_IA` — criar, enviar e importar lotes de enriquecimento de IA
- `3_Ranking` — ranking de artigos por score e escopo
- `4_Clusters` — agrupamento tematico de noticias
- `5_Editorial` — aprovar, rejeitar e baixar artigos do fluxo editorial
- `6_Entidades` — entidades extraidas (pessoas, organizacoes, lugares)
- `7_Alertas` — alertas e anomalias operacionais
- `8_Fontes_RSS` — gerenciar fontes RSS

O dashboard nao deve guardar regra de negocio principal. Toda decisao editorial precisa refletir no PostgreSQL.
Ele opera como fallback manual se Telegram ou n8n falharem.

Ele nao deve guardar regra de negocio principal. Toda decisao editorial precisa refletir no PostgreSQL.

## Docker

```powershell
docker compose up -d
```

Servicos:

- `postgres`: banco oficial do sistema.
- `app`: API Python na porta `8888`.
- `dashboard`: Streamlit na porta interna `8501`.
- `n8n`: orquestracao.
- `caddy`: HTTPS e proxy reverso.

## Testes

```powershell
pytest
```

O teste real de schema em PostgreSQL e opcional:

```powershell
$env:TEST_DATABASE_URL="postgresql://news:senha@localhost:5432/news_radar_test"
pytest tests\test_db_and_card_smoke.py
```

## Fase 2

- Publicacao automatica em Instagram ou outros canais.
- Painel publico ou frontend React/Next.
- Gerenciamento avancado de permissoes editoriais.
- Observabilidade completa com metricas e tracing.
- Migrador versionado dedicado, caso o schema cresca bastante.
