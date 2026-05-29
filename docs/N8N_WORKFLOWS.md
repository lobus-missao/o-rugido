# n8n Workflows — News Radar

Dois workflows cobrem toda a automação editorial. O Python controla 100% da lógica de negócio; o n8n apenas agenda e faz chamadas HTTP.

---

## Scheduler Interno (alternativa ao n8n)

A partir da Fase 1, o sistema tem um **scheduler interno opcional** baseado em APScheduler
que pode substituir o n8n como agendador.

| Modo | Scheduler | Ativação |
|------|-----------|---------|
| Padrão (atual) | n8n | — |
| Interno | APScheduler | `NEWS_RADAR_SCHEDULER=1` no `.env` |

**Como ativar o scheduler interno:**
1. Adicionar `NEWS_RADAR_SCHEDULER=1` ao `.env`
2. Reiniciar `api_server.py`
3. Confirmar em `GET /api/scheduler/status` que `running: true`
4. (Opcional) Desabilitar os workflows do n8n para evitar duplo disparo

**Segurança durante transição:** o guard de idempotência em `create_dispatch()`
bloqueia envios duplicados ao Telegram caso n8n e scheduler interno disparem
ao mesmo tempo. É seguro ter ambos ativos temporariamente.

**Para desativar:** `NEWS_RADAR_SCHEDULER=0` (ou remover a variável) e reiniciar.

**⚠️ Aviso multi-worker:** o scheduler interno usa `BackgroundScheduler`, compatível
apenas com Flask single-process. Ver `src/news_radar/scheduler.py` para detalhes.

---

## Estratégia Telegram: Estratégia A (telegram_poller.py)

O `telegram_poller.py` é o único processador de callbacks do Telegram no MVP local.
**Não configure webhook Telegram enquanto o poller estiver ativo** — são mutuamente exclusivos.

```
Telegram Bot API
    │
    ├── getUpdates  ←── telegram_poller.py  (Estratégia A — MVP local)
    └── webhook     ←── n8n (Estratégia B — produção com HTTPS público)
```

Para o MVP local, manter apenas o poller ativo.

---

## Arquivos

| Arquivo | Função |
|---------|--------|
| `n8n/workflows/01_coleta.json` | Coleta RSS a cada 30 min |
| `n8n/workflows/02_dispatch.json` | Dispara edições morning / noon / evening |
| `n8n-workflow.json` (raiz) | Legado — usa shell commands antigos, não usar |

---

## Variáveis de Ambiente no n8n

Configurar em: **Settings > Variables**

| Variável | Valor local | Valor Docker |
|----------|-------------|--------------|
| `NEWS_RADAR_API` | `http://localhost:8888` | `http://api:8888` |
| `NEWS_RADAR_SCOPE` | `piaui` | `piaui` |

> Sem essas variáveis os workflows falham na primeira execução. Configurar antes de ativar.

---

## Workflow 01 — Coleta Recorrente

**Arquivo:** `n8n/workflows/01_coleta.json`

**Fluxo:**
```
⏰ A cada 30 min
    → POST /pipeline/collect   {"limit_per_feed": 30}
    → POST /pipeline/rank
    → IF ok == false → Log erro (visível no n8n Executions)
```

**O que faz:**
- Puxa RSS das fontes configuradas em `configs/feeds.yaml`
- Calcula `final_score_brasil`, `final_score_piaui`, `final_score_teresina`
- Não envia nenhuma mensagem Telegram
- Erros ficam registrados no painel de execuções do n8n

**Endpoints chamados:**

```http
POST http://localhost:8888/pipeline/collect
Content-Type: application/json

{"limit_per_feed": 30}
```

```http
POST http://localhost:8888/pipeline/rank
Content-Type: application/json
```

---

## Workflow 02 — Dispatch Editorial

**Arquivo:** `n8n/workflows/02_dispatch.json`

**Fluxo:**
```
⏰ 06:30  →  POST /api/dispatch/run  {"edition": "morning", ...}
⏰ 11:30  →  POST /api/dispatch/run  {"edition": "noon",    ...}
⏰ 17:30  →  POST /api/dispatch/run  {"edition": "evening", ...}
```

Cada trigger é independente — falhar um não afeta os outros.

**O que faz (via `dispatch.py`):**
1. Seleciona top 3 artigos da janela de tempo da edição
2. Cria registros `dispatches` no PostgreSQL com `status = pending_article`
3. Envia cada artigo para o Telegram com botões `✅ Aprovar` / `❌ Rejeitar`
4. Retorna `{"ok": true, "count": 3, "dispatches": [...]}`

**Endpoint chamado:**

```http
POST http://localhost:8888/api/dispatch/run
Content-Type: application/json

{
  "edition": "morning",
  "scope": "piaui",
  "top": 3,
  "dry_run": false
}
```

**Valores válidos para `edition`:** `morning` | `noon` | `evening`

---

## Workflow de Callback Telegram (não existe no MVP)

Com Estratégia A, callbacks chegam diretamente ao `telegram_poller.py`.
O endpoint `POST /api/telegram/callback` existe na API mas **não é usado no MVP local**.

Se futuramente migrar para Estratégia B (webhook via n8n):
1. Registrar webhook: `python -c "from news_radar.telegram_sender import set_webhook; set_webhook('https://SEU_DOMINIO/webhook/telegram-approval')"`
2. Parar o `telegram_poller.py`
3. Criar workflow n8n: `Telegram Trigger → POST /api/telegram/callback`
4. **Nunca** rodar poller e webhook ao mesmo tempo

---

## Como Importar no n8n

1. Abrir n8n > Menu > **Import from File**
2. Selecionar `n8n/workflows/01_coleta.json`
3. Repetir para `02_dispatch.json`
4. Configurar variáveis em Settings > Variables (ver tabela acima)
5. Ativar os dois workflows

### Ajuste para versões antigas do HTTP Request node

Se o n8n exibir erro no body dos nós HTTP Request, abrir o nó e verificar:
- **Body Content Type** deve estar como `JSON`
- Colar o body manualmente se necessário

---

## Como Testar em Dry-Run

### Testar coleta manualmente

```powershell
# Chamar direto na API (sem n8n)
Invoke-WebRequest -Method POST http://localhost:8888/pipeline/collect `
  -ContentType "application/json" `
  -Body '{"limit_per_feed": 5}'
```

### Testar dispatch em dry-run

```powershell
# dry_run: true — cria dispatches no banco, NÃO envia Telegram
Invoke-WebRequest -Method POST http://localhost:8888/api/dispatch/run `
  -ContentType "application/json" `
  -Body '{"edition": "morning", "scope": "piaui", "top": 3, "dry_run": true}'
```

Verificar resultado no Streamlit > Edições.

### Ativar dry-run global (via .env)

```powershell
# Adicionar ao .env
NEWS_RADAR_DRY_RUN=1
```

Com essa variável, qualquer chamada à API ignora envios Telegram.

---

## Como Testar em Modo Real

**Pré-requisitos:**

```powershell
# 1. Variáveis no .env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# 2. API rodando
python api_server.py

# 3. Poller rodando (terminal separado)
python scripts/telegram_poller.py
```

**Executar dispatch manual:**

```powershell
Invoke-WebRequest -Method POST http://localhost:8888/api/dispatch/run `
  -ContentType "application/json" `
  -Body '{"edition": "morning", "scope": "piaui", "top": 3, "dry_run": false}'
```

Aguardar mensagens no Telegram. Clicar em Aprovar/Rejeitar.
Verificar status no Streamlit > Edições.

**Verificar status das edições:**

```powershell
Invoke-WebRequest http://localhost:8888/api/dispatch/status?date=2026-05-28
```

---

## Checklist de Validação Manual

### Setup inicial

- [ ] n8n rodando e acessível
- [ ] Variáveis `NEWS_RADAR_API` e `NEWS_RADAR_SCOPE` configuradas no n8n
- [ ] `api_server.py` respondendo em `GET http://localhost:8888/health`
- [ ] `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`
- [ ] `telegram_poller.py` rodando em terminal separado
- [ ] Workflows `01_coleta` e `02_dispatch` importados e **ativos**

### Teste de coleta

- [ ] Executar workflow 01 manualmente no n8n (botão "Execute Workflow")
- [ ] Verificar saída: `{"ok": true, "inserted": N}`
- [ ] Confirmar artigos no Streamlit > Ranking

### Teste de dispatch dry-run

- [ ] Executar `POST /api/dispatch/run` com `dry_run: true`
- [ ] Verificar `{"ok": true, "count": 3, "dry_run": true}` no retorno
- [ ] Confirmar dispatches criados no Streamlit > Edições
- [ ] Confirmar que **nenhuma mensagem** chegou no Telegram

### Teste de dispatch real

- [ ] Executar `POST /api/dispatch/run` com `dry_run: false`
- [ ] Confirmar 3 mensagens no Telegram com botões de aprovação
- [ ] Clicar em "✅ Aprovar" na notícia 1
- [ ] Confirmar que o poller processa e retorna status no terminal
- [ ] Confirmar que o card PNG é gerado e enviado ao Telegram
- [ ] Clicar em "✅ Publicar" no card
- [ ] Confirmar status `ready_to_publish` no Streamlit > Edições

### Fluxo completo estado final

- [ ] `dispatches.status = ready_to_publish`
- [ ] `articles.editorial_status = ready_to_publish`
- [ ] `articles.card_status = approved`
- [ ] Baixa manual pelo Streamlit: clicar "Marcar como publicado"
- [ ] Status final: `published`

---

## Payloads de Referência

### POST /api/dispatch/run

```json
{
  "edition": "morning",
  "scope": "piaui",
  "top": 3,
  "dry_run": false
}
```

Resposta esperada:
```json
{
  "ok": true,
  "edition": "morning",
  "scope": "piaui",
  "dry_run": false,
  "count": 3,
  "dispatches": [
    {"dispatch_id": 101, "rank": 1, "article": {...}},
    {"dispatch_id": 102, "rank": 2, "article": {...}},
    {"dispatch_id": 103, "rank": 3, "article": {...}}
  ]
}
```

### POST /api/telegram/callback (Estratégia B — não usar no MVP)

```json
{
  "callback_query": {
    "data": "dispatch_approve:101",
    "from": {
      "first_name": "Roberto",
      "username": "roberto"
    }
  }
}
```

### GET /api/dispatch/status

```
GET /api/dispatch/status?date=2026-05-28&edition=morning
```

Resposta esperada:
```json
{
  "ok": true,
  "date": "2026-05-28",
  "editions": {
    "morning": [
      {
        "id": 101,
        "status": "ready_to_publish",
        "rank": 1,
        "title": "...",
        "article_reviewed_by": "Roberto",
        "card_reviewed_by": "Roberto"
      }
    ]
  }
}
```

---

## Referência de Estados

| Status | Significado |
|--------|-------------|
| `pending_article` | Enviado ao Telegram, aguardando aprovação da notícia |
| `article_approved` | Notícia aprovada, card sendo gerado |
| `article_rejected` | Notícia rejeitada pelo editor |
| `pending_card` | Card enviado ao Telegram, aguardando aprovação |
| `card_rejected` | Card rejeitado — regenerar via Streamlit ou callback |
| `ready_to_publish` | Card aprovado, pronto para postagem manual |
| `published` | Baixa manual concluída no Streamlit |
