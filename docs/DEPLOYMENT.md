# Guia de Deploy — News Radar RSS

> Passo a passo para subir o sistema do zero, em ambiente local ou produção.
> Versão: Fase 9 · 2026-05-29

---

## Pré-requisitos

| Ferramenta | Versão mínima | Notas |
|---|---|---|
| Docker | 24+ | Com Docker Compose integrado |
| Python | 3.12+ | Apenas para desenvolvimento local |
| PostgreSQL | 15+ | Incluso no Docker Compose |
| Telegram Bot | — | Opcional; sem bot, aprovação é via dashboard |

---

## Deploy local (desenvolvimento)

### 1. Clonar e configurar ambiente

```bash
git clone <repo> news_radar_rss
cd news_radar_rss

# Criar ambiente virtual Python
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r requirements.txt
pip install -e .

# Instalar Playwright Chromium (para geração de PNG)
playwright install chromium
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com seus valores:
# - DATABASE_URL (PostgreSQL local)
# - TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (opcional)
```

### 3. Subir PostgreSQL (via Docker)

```bash
docker run -d \
  --name news-postgres \
  -e POSTGRES_USER=news \
  -e POSTGRES_PASSWORD=senha \
  -e POSTGRES_DB=news_radar \
  -p 5432:5432 \
  postgres:16-alpine
```

### 4. Inicializar banco

```bash
python -m news_radar.cli init-db
```

### 5. Seed de fontes (primeira vez)

```bash
python scripts/seed_sources.py
```

### 6. Primeira coleta

```bash
python -m news_radar.cli collect --limit-per-feed 10
python -m news_radar.cli rank
```

### 7. Rodar API e Dashboard

```bash
# Terminal 1 — API Flask
python api_server.py

# Terminal 2 — Dashboard Streamlit
streamlit run dashboard.py --server.port 8501
```

---

## Deploy com Docker Compose (produção local)

### 1. Configurar .env

```bash
cp .env.example .env
```

Edite `.env` obrigatoriamente:
```env
POSTGRES_USER=news
POSTGRES_PASSWORD=<senha_forte>
TELEGRAM_BOT_TOKEN=<token_do_botfather>
TELEGRAM_CHAT_ID=<id_do_grupo_ou_canal>
DOMAIN=news.seudominio.com.br   # para HTTPS via Caddy
N8N_USER=admin
N8N_PASSWORD=<senha_n8n>
```

### 2. Build e subida

```bash
docker compose up -d --build
```

### 3. Inicializar banco dentro do container

```bash
docker exec news-radar-app-1 python -m news_radar.cli init-db
docker exec news-radar-app-1 python scripts/seed_sources.py
```

### 4. Verificar saúde

```bash
curl http://localhost:8888/health
# Esperado: {"status": "ok", ...}

# Dashboard
curl http://localhost:8501
```

### 5. Primeira coleta

```bash
docker exec news-radar-app-1 python -m news_radar.cli collect --limit-per-feed 20
docker exec news-radar-app-1 python -m news_radar.cli rank
```

---

## Deploy em produção com HTTPS (Caddy)

### Pré-requisito: domínio apontando para o servidor

```
news.seudominio.com.br → IP do servidor
```

### Caddyfile (já existe no repo)

```
news.seudominio.com.br {
    handle /n8n/* {
        reverse_proxy n8n:5678
    }
    handle /api/* {
        reverse_proxy app:8888
    }
    handle {
        reverse_proxy dashboard:8501
    }
}
```

### Subida com HTTPS

```bash
# Certifique-se de que DOMAIN está no .env
docker compose up -d --build
# Caddy obtém certificado Let's Encrypt automaticamente
```

---

## Verificação pós-deploy

```bash
# Checklist rápido
curl https://news.seudominio.com.br/api/health        # API HTTPS
curl https://news.seudominio.com.br/api/scheduler/status  # Scheduler

# Via dashboard: abrir https://news.seudominio.com.br
# → Radar mostra artigos? ✓
# → Operação mostra coletas recentes? ✓
# → Sem erros de banco? ✓
```

---

## Atualizações

```bash
git pull

# Recriar imagem Docker
docker compose up -d --build app dashboard

# Aplicar migrations pendentes
docker exec news-radar-app-1 python -m news_radar.cli init-db
```

---

## Playwright no Docker

O Dockerfile usa `playwright install chromium --with-deps` para instalar o Chromium bundled do Playwright. Isso:
- Baixa ~350MB de binário do Chromium durante o `docker build`
- Armazena em `/ms-playwright` dentro do container
- Funciona de forma confiável sem dependências extras do sistema

Se o build falhar na etapa do Playwright:
```bash
# Testar conectividade durante o build
docker build --network=host .

# Verificar se Playwright funciona no container
docker exec news-radar-app-1 python -c "
from news_radar.card_renderer import is_playwright_available
print('Playwright OK:', is_playwright_available())
"
```

---

## Backup e Restore

```bash
# Backup manual
docker exec news-radar-postgres-1 \
  pg_dump -U news news_radar > backup_$(date +%Y%m%d_%H%M%S).sql

# Ou via CLI (se pg_dump disponível localmente)
python -m news_radar.cli backup --output backup.sql

# Restore
psql "postgresql://news:senha@localhost:5432/news_radar" < backup.sql

# Restore via Docker
docker exec -i news-radar-postgres-1 \
  psql -U news news_radar < backup.sql
```

---

## Variáveis opcionais de ajuste fino

```env
# Scheduler interno (alternativa ao n8n)
NEWS_RADAR_SCHEDULER=0         # 1 para ativar

# Escopo e tamanho do dispatch automático
NEWS_RADAR_DISPATCH_SCOPE=piaui
NEWS_RADAR_DISPATCH_TOP=3

# Dry-run global (sem envios reais ao Telegram)
NEWS_RADAR_DRY_RUN=0

# Chromium customizado (caso necessário)
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
```

---

## Resolução de problemas de deploy

| Sintoma | Causa provável | Ação |
|---|---|---|
| `app` não sobe | Banco não disponível | Aguardar `postgres` ficar healthy |
| `playwright install` falha | Sem internet no build | Usar `--network=host` no docker build |
| Dashboard 502 | `dashboard` não iniciou | `docker logs news-radar-dashboard-1` |
| Cards sem PNG | Playwright não instalado | Ver seção "Playwright no Docker" |
| HTTPS não funciona | Domínio não aponta para o servidor | Verificar DNS |
