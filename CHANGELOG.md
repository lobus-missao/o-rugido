# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
O projeto ainda não segue [SemVer](https://semver.org/lang/pt-BR/) — versões são datadas.

## [Não lançado]

### Corrigido
- Endpoint `/pipeline/*` retornava 500 depois de 180s em rede lenta. Agora chama services direto, sem subprocess. (#47)
- Captions do Telegram quebravam com títulos que tinham `_`, `*`, `[`, `<script>` etc. Migrado para HTML mode com escape. (#46)
- Imagens de `lookaside.instagram.com`, `cdninstagram.com`, `fbcdn.net` etc. viravam candidato e falhavam com 403. Agora filtradas antes da tentativa de download. (#43)

### Alterado
- `dashboard/app.py` → `dashboard/Home.py` (padrão de multipage do Streamlit).
- Reorganização das páginas do dashboard em Home + Edições + Operação + Monitoramento.
- Package Python `news_radar` → `o_rugido`. Env vars `NEWS_RADAR_*` → `O_RUGIDO_*`.
- Postgres passa a usar o Docker padrão da plataforma da Missão em vez de container próprio.

### Adicionado
- Página Monitoramento no dashboard com health de API, host, BD, Telegram, Serper, containers e workflows do n8n.
- Endpoint `POST /monitor/dispatch-alerts` que despacha alertas críticos pro Telegram admin com dedupe.
- `docs/pipeline-flowchart.md` com fluxo do produto em Mermaid.

### Segurança
- Histórico do git limpo do token do Telegram vazado.
- `memory/` e `notes/` no `.gitignore` — não vão pro repo.
