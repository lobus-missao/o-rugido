# News Radar

Pipeline editorial para Piauí: coleta RSS, ranqueia por relevância, gera card visual, aprovação humana via Telegram e publicação em Telegram + Instagram.

## Stack

- Python 3.12 · PostgreSQL · Flask · Streamlit
- Playwright (HTML → PNG) · APScheduler · n8n
- Pydantic 2 · feedparser · trafilatura

## Arquitetura

Estrutura layered, camadas independentes:

```
src/news_radar/
├── api/          rotas Flask (5 endpoints — só extração + scoring)
├── core/         db, config, text_utils, cache
├── services/     casos de uso (ingestion, ranker, editorial, rendering, classifier)
├── repositories/ acesso ao banco
├── adapters/     integrações externas (webhook n8n)
├── cli.py
└── scheduler.py

dashboard/   Streamlit (app.py + components.py + 2 páginas)
tests/       183 testes
```

Regra de dependência: `api → services → repositories | adapters → core`. n8n orquestra publicação externa (Telegram, Instagram) via HTTP — fora do Python.

## Setup local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

PostgreSQL via Docker:

```powershell
docker compose -f docker-compose.dev.yml up -d
```

Aplicar schema:

```powershell
python -m news_radar.cli init-db
```

Configurar `.env` a partir de `.env.example`.

## Uso

```powershell
python -m news_radar.cli collect        # coleta RSS
python -m news_radar.cli rank           # recalcula scores
python -m news_radar.cli show           # lista top artigos
python -m news_radar.cli make-card      # gera PNG dos artigos pendentes
python -m news_radar.cli dispatch       # cria envio editorial
python -m news_radar.cli stats          # métricas do banco

streamlit run dashboard/app.py          # dashboard (aprovação + saúde)
python api_server.py                    # API HTTP (porta 8888)
```

## Fluxo

```
RSS (feedparser) → ingestion → ranker (score Piauí) → PostgreSQL
                                                         ↓
                                                  n8n (webhook)
                                                         ↓
                          render card (HTML+Playwright)  ↓
                                                         ↓
                              Telegram (aprovação humana) ←→ callback n8n
                                                         ↓
                                                  publicação
                                       (Telegram + Instagram via n8n)
```

API expõe apenas extração e scoring. n8n é o orquestrador externo.

## Testes

```powershell
pytest
```

183 testes, ~3s.

## Deploy

Ver `docs/DEPLOYMENT.md`.
