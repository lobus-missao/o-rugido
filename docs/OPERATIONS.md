# Guia de Operações — News Radar RSS

> Referência diária para operar o sistema sem precisar de memória do desenvolvedor.
> Versão: Fase 9 · 2026-05-29

---

## Verificação rápida de saúde

```bash
# API Flask respondendo?
curl http://localhost:8888/health

# Scheduler ativo?
curl http://localhost:8888/api/scheduler/status

# Dashboard abrindo?
# Acesse: http://localhost:8501

# Banco com artigos?
python -m news_radar.cli stats
```

---

## Ciclo editorial diário

### 1. Coletar feeds

```bash
# Coleta RSS de todos os feeds habilitados (~57 fontes)
python -m news_radar.cli collect --limit-per-feed 30

# Via Docker
docker exec news-radar-app-1 python -m news_radar.cli collect --limit-per-feed 30
```

### 2. Recalcular ranking

```bash
python -m news_radar.cli rank
```

### 3. Gerar lotes de IA (quando necessário)

```bash
# Gera lote para o escopo principal
python -m news_radar.cli make-ai-batches --scope piaui --top 100 --days-back 2

# Lista lotes pendentes
python -m news_radar.cli list-ai-batches --status pending
```

Copie o prompt gerado → Cole no ChatGPT ou Claude → Cole o JSON de volta na dashboard (página Lotes IA).

### 4. Agrupar artigos similares

```bash
python -m news_radar.cli cluster-articles --hours 72 --scope piaui
```

### 5. Disparar edição (se scheduler desativado)

```bash
# Edição da manhã, escopo Piauí, top 3 artigos
python -m news_radar.cli dispatch --edition morning --scope piaui --top 3

# Dry-run (não envia ao Telegram, só cria registros)
python -m news_radar.cli dispatch --edition morning --scope piaui --dry-run
```

### 6. Gerar cards PNG

```bash
python -m news_radar.cli make-card --scope piaui --limit 3
```

---

## Manutenção

### Limpeza de artigos velhos

```bash
# Remove artigos sem IA com mais de 30 dias, expira lotes pending > 48h
python -m news_radar.cli cleanup --days 30 --expire-batches-hours 48
```

### Backup do banco

```bash
# Requer pg_dump instalado no sistema
python -m news_radar.cli backup --output backup_$(date +%Y%m%d).sql

# Via Docker (sem pg_dump local)
docker exec news-radar-postgres-1 pg_dump -U news news_radar > backup_$(date +%Y%m%d).sql

# Restore
psql "postgresql://news:senha@localhost:5432/news_radar" < backup_20260529.sql
```

### Re-inicializar banco (migrations seguras)

```bash
# Aplica apenas migrations pendentes — seguro de rodar repetidamente
python -m news_radar.cli init-db
```

---

## Scheduler interno

O scheduler Python interno é uma alternativa ao n8n para coleta e dispatch automáticos.

```bash
# Ativar (apenas se não estiver usando n8n)
export NEWS_RADAR_SCHEDULER=1
# ou no .env: NEWS_RADAR_SCHEDULER=1

# Status
curl http://localhost:8888/api/scheduler/status

# Jobs agendados:
# - collect + rank: a cada 30min
# - dispatch morning: 06:30 (escopo configurado em NEWS_RADAR_DISPATCH_SCOPE)
# - dispatch noon:    11:30
# - dispatch evening: 17:30
```

**Atenção:** Ativar `NEWS_RADAR_SCHEDULER=1` com n8n também ativo pode causar duplo disparo. O guard de idempotência em `create_dispatch()` protege contra duplicação, mas é recomendado usar apenas um dos dois schedulers.

---

## Logs e monitoramento

```bash
# Logs do container app
docker logs news-radar-app-1 --tail 100 -f

# Logs do dashboard
docker logs news-radar-dashboard-1 --tail 50

# Últimas coletas no banco
# Na dashboard: página "Operação" → log de coletas

# Artigos críticos sem IA
# Na dashboard: página "Alertas"
```

---

## Variáveis de ambiente essenciais

| Variável | Descrição | Padrão |
|---|---|---|
| `DATABASE_URL` | Conexão PostgreSQL | `postgresql://news:senha@localhost:5432/news_radar` |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram | vazio |
| `TELEGRAM_CHAT_ID` | ID do canal/grupo editorial | vazio |
| `NEWS_RADAR_SCHEDULER` | Scheduler interno (0=off, 1=on) | `0` |
| `NEWS_RADAR_DISPATCH_SCOPE` | Escopo do dispatch automático | `piaui` |
| `NEWS_RADAR_DRY_RUN` | Desativa envios reais ao Telegram | `0` |
| `PLAYWRIGHT_BROWSERS_PATH` | Onde playwright busca o Chromium | `/ms-playwright` |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | Override do executável Chromium | (detectado automaticamente) |

---

## Portas padrão

| Serviço | Porta | URL |
|---|---|---|
| API Flask | 8888 | `http://localhost:8888` |
| Dashboard Streamlit | 8501 | `http://localhost:8501` |
| PostgreSQL | 5432 | `postgresql://localhost:5432/news_radar` |
| n8n | (interno) | via Caddy em `/n8n/` |

---

## Endpoints úteis da API

```bash
GET  /health                          # saúde da API
GET  /api/scheduler/status            # status do scheduler
POST /pipeline/collect                # coletar feeds
POST /pipeline/rank                   # recalcular ranking
POST /api/dispatch/run                # disparar edição
POST /api/review/news                 # aprovar/rejeitar artigo
POST /api/review/card                 # aprovar/rejeitar card
```

---

## Resolução de problemas comuns

| Problema | Diagnóstico | Solução |
|---|---|---|
| Dashboard não abre | `docker logs dashboard` | Verificar DATABASE_URL |
| Cards sem PNG | `is_playwright_available()` retorna False | `playwright install chromium` |
| Telegram não recebe mensagens | Verificar TELEGRAM_BOT_TOKEN | Checar bot em @BotFather |
| Coleta para | n8n ou scheduler desativado | Ativar NEWS_RADAR_SCHEDULER=1 ou reiniciar n8n |
| Banco cheio de artigos antigos | `stats` mostra total alto | `cleanup --days 30` |
| init-db falha | Banco indisponível | `docker ps` — verificar se postgres está rodando |
