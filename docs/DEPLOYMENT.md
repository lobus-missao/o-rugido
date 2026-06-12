# Guia de Deploy — News Radar RSS

> Passo a passo para subir o sistema em desenvolvimento local ou na plataforma da Missão (homolog/prod).

---

## Pré-requisitos

| Ferramenta | Versão mínima | Notas |
|---|---|---|
| Docker | 24+ | Com Docker Compose integrado |
| Python | 3.12+ | Apenas para desenvolvimento local |
| PostgreSQL | 15+ | Incluso no compose local; em homolog/prod vem da plataforma |
| Telegram Bot | — | Opcional; sem bot, aprovação é via dashboard |

---

## Composes disponíveis

| Arquivo | Para que serve |
|---|---|
| `docker-compose.yml` | **Dev local** — sobe postgres, n8n, searxng, app, dashboard e cloudflared em containers próprios. |
| `docker-compose.prod.yml` | **Homolog e prod na plataforma da Missão** — sobe apenas app, dashboard e searxng; conecta na rede externa `missao-network`, onde postgres e n8n são compartilhados. |

Templates de `.env`:
- `.env.example` → dev local
- `.env.homolog.example` → homolog
- `.env.prod.example` → prod

---

## Deploy local (desenvolvimento)

### 1. Clonar e configurar ambiente

```bash
git clone <repo> news-radar-rss
cd news-radar-rss

python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements-dev.txt
pip install -e .
playwright install chromium
```

### 2. Configurar .env

```bash
cp .env.example .env
# Edite TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, senhas
```

### 3. Subir PostgreSQL (e demais containers se quiser)

```bash
# só o postgres (rodar app/dashboard fora do container)
docker compose up -d postgres

# ou stack completa
docker compose up -d --build
```

### 4. Inicializar banco e seed

```bash
python -m news_radar.cli init-db
python scripts/seed_sources.py
```

### 5. Primeira coleta

```bash
python -m news_radar.cli collect --limit-per-feed 10
python -m news_radar.cli rank
```

### 6. Rodar API e Dashboard (se postgres rodando isolado)

```bash
# Terminal 1
python api_server.py

# Terminal 2
streamlit run dashboard/app.py --server.port 8501
```

---

## Deploy na plataforma da Missão (homolog / prod)

A plataforma já provê **Postgres, N8N, Redis e Ollama** rodando em containers separados na rede docker `missao-network`. O reverse proxy é feito pelo **NGINX Proxy Manager + Cloudflare** da plataforma.

Nosso compose sobe apenas: `app`, `dashboard`, `searxng`.

### 1. Preparar .env

Para homolog:
```bash
cp .env.homolog.example .env.homolog
# Preencha DATABASE_URL, TELEGRAM_BOT_TOKEN, etc. com os valores da infra.
```

Para prod:
```bash
cp .env.prod.example .env.prod
```

### 2. Subir os serviços

```bash
# homolog
docker compose -f docker-compose.prod.yml --env-file .env.homolog up -d --build

# prod
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

### 3. Inicializar banco (primeira vez)

```bash
docker exec news-radar-app python -m news_radar.cli init-db
docker exec news-radar-app python scripts/seed_sources.py
```

### 4. Verificar saúde

```bash
docker exec news-radar-app curl -s http://localhost:8888/health
# Esperado: {"status": "ok", ...}
```

Externamente (via NGINX Proxy Manager + Cloudflare):
```bash
curl https://news-radar-homolog.seudominio.com.br/health
```

---

## Atualizações

```bash
git pull

# homolog
docker compose -f docker-compose.prod.yml --env-file .env.homolog up -d --build app dashboard

# Aplicar migrations pendentes (idempotente)
docker exec news-radar-app python -m news_radar.cli init-db
```

---

## Playwright no Docker

O Dockerfile instala o Chromium bundled do Playwright em `/ms-playwright` durante o build (~350MB).

Se o build falhar na etapa do Playwright:
```bash
docker build --network=host .

docker exec news-radar-app python -c "from news_radar.services.rendering import is_playwright_available; print('Playwright OK:', is_playwright_available())"
```

---

## Backup e Restore

```bash
# Backup (dev local)
docker exec news-radar-rss-postgres-1 \
  pg_dump -U news news_radar > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup (homolog/prod) — direto no postgres compartilhado da plataforma
docker exec <container-postgres-plataforma> \
  pg_dump -U <usuario> news_radar > backup.sql

# Restore
psql "postgresql://news:senha@localhost:5432/news_radar" < backup.sql
```

---

## Variáveis opcionais de ajuste fino

```env
# Scheduler interno (1 = APScheduler, 0 = N8N agenda)
NEWS_RADAR_SCHEDULER=0

# Escopo e tamanho do dispatch automático
NEWS_RADAR_DISPATCH_SCOPE=piaui
NEWS_RADAR_DISPATCH_TOP=3

# Dry-run global (sem envios reais ao Telegram)
NEWS_RADAR_DRY_RUN=0

# Chromium customizado
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
```

---

## Resolução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `app` não sobe | Banco indisponível | Conferir `DATABASE_URL` e se postgres responde |
| `playwright install` falha no build | Sem internet | `docker build --network=host .` |
| Dashboard 502 | Container não iniciou | `docker logs news-radar-dashboard` |
| Cards sem PNG | Playwright não instalado | Ver seção "Playwright no Docker" |
| HTTPS não funciona | DNS / NGINX Proxy Manager | Conferir com a infra da plataforma |
| `missao-network` não existe | Rede não criada pela infra | Pedir à infra para criar/expor a rede |
