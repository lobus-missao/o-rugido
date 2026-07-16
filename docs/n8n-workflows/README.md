# Workflows n8n — Portal O Rugido

Dois workflows independentes. Triggers diferentes (Schedule vs Telegram callback) e responsabilidades distintas.

## Os 2 workflows

| Arquivo | Trigger | O que faz |
|---|---|---|
| `01-coleta-e-aprovacao.json` | Schedule (7h, 12h, 18h) | Coleta RSS → ranqueia → seleciona top 3 → busca imagem no Serper.dev → gera card → envia pro Telegram com botões aprovar/rejeitar |
| `02-publicacao.json` | Telegram callback_query | Recebe clique no botão → publica no canal Telegram + Instagram (se aprovado) ou marca como rejeitado |

## Como importar

Pra cada arquivo:

1. n8n UI → Workflows → "Import from File"
2. Configurar credenciais nos nós marcados `REPLACE_ID`
3. Definir variáveis de ambiente (Settings → Variables)
4. Salvar e ativar

Use a mesma credencial Postgres e Telegram nos 2 workflows.

## Credenciais necessárias (configurar 1x cada)

### Postgres
- Host: `postgres` (container) ou IP
- Database: `o_rugido`
- User / Password: do `.env`
- Port: `5432`

### Telegram API
- Access Token do `@BotFather`

## Variáveis de ambiente

Configurar em **Settings → Variables** do n8n (ou via env do container):

```
O_RUGIDO_API_URL=http://app:8888
O_RUGIDO_PUBLIC_URL=https://seudominio.com.br

SERPER_API_KEY=...

TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_APPROVER_CHAT_ID=123456789
TELEGRAM_FINAL_CHANNEL=@seu_canal_publico

INSTAGRAM_ACCESS_TOKEN=EAAxxx...
INSTAGRAM_BUSINESS_ID=17841...
```

## Fluxo

### Workflow 01 — Coleta e Aprovação

```
[Schedule 7h/12h/18h]
  → POST /pipeline/collect
  → POST /pipeline/rank
  → Postgres SELECT top 3
  → Loop por artigo:
       → Serper Images (busca imagem real do Google Images via Serper.dev)
       → Extrai image_url
       → POST /cards/render
       → Telegram sendPhoto com inline_keyboard
       → Postgres UPDATE pending_approval
```

### Workflow 02 — Publicação

```
[Telegram callback_query]
  → Parse action + article_id
  → IF aprovado?
      ├─ TRUE  → busca artigo → Telegram canal → Instagram container → Instagram publish → UPDATE published
      └─ FALSE → UPDATE rejected
  → Telegram answerCallback (limpa loading do botão)
```

## Ordem de ativação

1. Ativar **02-publicacao** primeiro (precisa estar escutando antes de clicar no botão)
2. Depois ativar **01-coleta-e-aprovacao**

## Setup das credenciais externas

### 1. Telegram Bot
1. `@BotFather` → `/newbot` → recebe TOKEN
2. Manda msg ao bot
3. `https://api.telegram.org/bot{TOKEN}/getUpdates` → copia `chat.id`
4. Cria canal público, adiciona bot como admin

### 2. Serper.dev (busca de imagem)
1. `https://serper.dev/signup` (sem cartão)
2. Dashboard → copia API Key
3. Free tier 2.500 buscas/mês — cobre ~28 meses do uso (90/mês)

### 3. Instagram Graph API
1. Conta Instagram **Business** ou **Creator** conectada a uma Facebook Page
2. `developers.facebook.com` → app Business → produto Instagram Graph API
3. Page Access Token de longa duração (60 dias)
4. Instagram Business Account ID via Graph API Explorer

## Notas

- Cloudflare Tunnel precisa estar ativo apontando `O_RUGIDO_PUBLIC_URL` pra API (porta 8888). Sem isso, Instagram não consegue baixar o card de `/cards/*.png`.
- Em dev local: `cloudflared tunnel --url http://localhost:8888` cria URL temporária `*.trycloudflare.com`.
- Aprovação é assíncrona: se não responder na hora, o artigo fica `pending_approval` no banco — pode aprovar depois sem perder.
