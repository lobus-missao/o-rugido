# Operacao Editorial

Este playbook descreve o fluxo operacional do MVP. O PostgreSQL e a fonte oficial de estado; Streamlit, Telegram e n8n apenas operam esse estado.

## Fluxo principal

```text
collect -> rank -> dispatch Top 3 -> aprovar noticia -> gerar card
-> aprovar card -> ready_to_publish -> baixa manual/publicado
```

## Coleta e ranking

```powershell
python -m news_radar.cli init-db
python -m news_radar.cli collect --limit-per-feed 25
python -m news_radar.cli rank
python -m news_radar.cli stats
```

## Disparar uma edicao

Edicoes disponiveis:

- `morning`: janela de 13h, postagem prevista 7h.
- `noon`: janela de 5h, postagem prevista 12h.
- `evening`: janela de 6h, postagem prevista 18h.

Disparo real:

```powershell
python -m news_radar.cli dispatch --edition morning --scope piaui --top 3
```

Teste sem Telegram real:

```powershell
python -m news_radar.cli dispatch --edition morning --scope piaui --top 3 --dry-run
```

Tambem e possivel ativar dry-run por ambiente:

```powershell
$env:NEWS_RADAR_DRY_RUN="1"
```

## Aprovacao no Telegram

O dispatch envia cada noticia com botoes:

- `dispatch_approve:{dispatch_id}` aprova a noticia.
- `dispatch_reject:{dispatch_id}` rejeita a noticia.

Ao aprovar a noticia pelo Telegram, o sistema registra:

- `dispatches.article_reviewed_by`;
- `dispatches.article_reviewed_at`;
- `dispatches.status = article_approved`;
- card gerado e enviado para aprovacao.

Depois o card recebe botoes:

- `card_approve:{dispatch_id}` aprova o card.
- `card_reject:{dispatch_id}` rejeita o card.
- `card_regenerate:{dispatch_id}` regera o card.

Ao aprovar o card, o sistema registra:

- `dispatches.card_reviewed_by`;
- `dispatches.card_reviewed_at`;
- `dispatches.ready_at`;
- `dispatches.status = ready_to_publish`;
- `articles.editorial_status = ready_to_publish`;
- `articles.card_status = approved`.

## Baixa manual

Depois da postagem manual, marque como publicado:

```powershell
python -m news_radar.cli mark-published --dispatch-id 123
```

No Streamlit, use a pagina `Edicoes` para ver a edicao do dia e clicar em `Marcar como publicado`.

## Verificar no Streamlit

```powershell
streamlit run dashboard.py
```

Use:

- `Edicoes` para acompanhar morning/noon/evening.
- `Ranking` para validar as noticias selecionadas.
- `Lotes de IA` para enriquecer ou importar IA manualmente.
- `Editorial` para acompanhar status.
- `Alertas` para pendencias operacionais.

## Endpoints para n8n

Base local:

```text
http://localhost:8888
```

### GET /api/editorial/top3

Consulta os candidatos da edicao.

```http
GET /api/editorial/top3?edition=morning&scope=piaui&top=3
```

### POST /api/dispatch/run

Cria dispatches e envia Top 3 ao Telegram.

```json
{
  "edition": "morning",
  "scope": "piaui",
  "top": 3,
  "dry_run": false
}
```

### POST /api/review/news

Aprova ou rejeita uma noticia.

```json
{
  "dispatch_id": 123,
  "action": "approve",
  "reviewer": "Roberto",
  "generate_card": false,
  "dry_run": false
}
```

Para rejeitar:

```json
{
  "dispatch_id": 123,
  "action": "reject",
  "reviewer": "Roberto"
}
```

### POST /api/cards/generate

Gera card para uma noticia aprovada e envia para aprovacao.

```json
{
  "dispatch_id": 123,
  "reviewer": "Roberto",
  "dry_run": false
}
```

### POST /api/review/card

Aprova ou rejeita um card.

```json
{
  "dispatch_id": 123,
  "action": "approve",
  "reviewer": "Roberto",
  "dry_run": false
}
```

### GET /api/dispatch/status

Consulta o estado das edicoes.

```http
GET /api/dispatch/status?date=2026-05-28
GET /api/dispatch/status?edition=morning&date=2026-05-28
```

### POST /api/telegram/callback

Endpoint util para receber payload bruto do Telegram via n8n.

```json
{
  "callback_query": {
    "data": "card_approve:123",
    "from": {
      "first_name": "Roberto",
      "username": "roberto"
    }
  }
}
```

## Estados principais

- `pending_article`: noticia enviada para aprovacao.
- `article_approved`: noticia aprovada, card pode ser gerado.
- `article_rejected`: noticia rejeitada.
- `pending_card`: card enviado para aprovacao.
- `card_rejected`: card rejeitado.
- `ready_to_publish`: card aprovado, pronto para postagem manual.
- `published`: baixa manual concluida.
