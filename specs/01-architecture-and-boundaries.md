# Spec 01 — Arquitetura e Fronteiras

**Status:** Aprovado
**Fase:** 0 — Diagnóstico e SDD

---

## Módulos do Sistema

### 1. Ingestão (`collector.py` + futuros adapters)
- Responsabilidade: buscar conteúdo de fontes externas e salvar no banco
- Entrada: `sources` / `feeds.yaml`
- Saída: registros em `articles` + `feed_runs`
- Não decide o que publicar — apenas coleta

### 2. Normalização (dentro de `collector.py::normalize_entry`)
- Responsabilidade: limpar, padronizar e enriquecer dados brutos
- Entrada: entrada bruta do RSS/API
- Saída: campos normalizados (title, canonical_url, summary, published_at, etc.)
- Deve preservar `raw_json` inalterado

### 3. Ranking (`ranker.py`)
- Responsabilidade: calcular scores por múltiplas dimensões
- Entrada: campos do artigo normalizado
- Saída: `auto_score_*`, `final_score_*` (com IA quando disponível)
- Pesos configuráveis futuramente

### 4. IA Assistida (`ai_batches.py`)
- Responsabilidade: gerar prompts, importar resultados de IA
- Entrada: artigos selecionados do banco
- Saída: prompts em arquivo + resultados importados no banco
- Não chama API de IA diretamente

### 5. Deduplicação / Clustering (`collector.py` + futuro `clusters.py`)
- Responsabilidade: evitar duplicatas e agrupar por assunto
- Entrada: artigos novos
- Saída: `canonical_url` único, `story_clusters` futuros

### 6. Fluxo Editorial (`dispatch.py`)
- Responsabilidade: selecionar artigos, enviar para aprovação, controlar estados
- Entrada: artigos com score + comando de edição
- Saída: `dispatches` com status, Telegram messages

### 7. Card Renderer (`card_renderer.py`)
- Responsabilidade: gerar imagem PNG a partir de template HTML
- Entrada: dados do artigo + template
- Saída: PNG em `data/cards/`

### 8. Dashboard (`dashboard.py` + `pages/`)
- Responsabilidade: interface editorial completa
- Entrada: dados do banco
- Saída: ações do editor (aprovação, rejeição, geração de lotes, etc.)

### 9. API Flask (`api_server.py`)
- Responsabilidade: bridge HTTP para integrações externas
- Entrada: requisições HTTP de n8n ou outros sistemas
- Saída: JSON responses delegando para CLI/Python

### 10. CLI (`cli.py`)
- Responsabilidade: interface de linha de comando para todas as operações
- Cada comando é atômico e retorna JSON
- É chamado pela API Flask via `subprocess.run`

---

## Responsabilidades por Camada

| Camada | O que decide | O que NÃO decide |
|--------|--------------|-----------------|
| Python Backend | Score, status, lógica de aprovação | Como exibir, quando agendar |
| Dashboard | Quais filtros mostrar, qual ação disparar | Score, lógica de aprovação |
| API Flask | Como expor endpoints HTTP | Lógica de negócio |
| n8n | Quando chamar endpoints | O que fazer com dados |
| Telegram | Canal de notificação | Estado editorial |
| IA | Classificação e sugestão | Decisão de publicação |

---

## Fronteiras Críticas

### Banco é a Fonte de Verdade
```
REGRA: Todo estado editorial vive no PostgreSQL.
Não usar: arquivos .json como estado canônico, variáveis n8n, memória do bot Telegram.
Exceção aceitável: prompts e resultados de IA em data/ como cache (banco tem referência ao path).
```

### Dashboard Controla Estados Editoriais
```
REGRA: Qualquer mudança de editorial_status deve passar pelo banco.
A dashboard chama módulos Python que atualizam o banco.
Não atualizar estado editorial diretamente de webhooks n8n.
```

### n8n Não Contém Regra de Negócio
```
REGRA: n8n apenas agenda chamadas HTTP ou encaminha webhooks.
Exemplos do que NÃO pode estar no n8n:
- Lógica de seleção de artigos
- Cálculo de scores
- Regras de deduplicação
- Critérios de aprovação
```

### IA é Assistente, Não Fonte Factual
```
REGRA: Dados da IA são sugestões, não fatos verificados.
- IDs retornados pela IA devem ser validados contra o banco
- Campos não reconhecidos são ignorados com log
- Rollback deve ser possível se importação causar problemas
- Editor tem sempre a palavra final
```

### CLI é a Interface Canônica de Operações
```
REGRA: Toda operação de negócio tem um comando CLI correspondente.
A API Flask chama o CLI (ou importa diretamente).
Isso garante que operações funcionem sem HTTP.
```

---

## Diagrama de Dependências

```
feeds.yaml / sources
    ↓
collector.py
    ↓ (psycopg2)
PostgreSQL ← → repository.py
    ↑               ↑
ranker.py       dashboard_queries.py
    ↑               ↑
ai_batches.py   dash_utils.py
    ↑               ↑
card_renderer.py    pages/*.py
    ↑               ↑
dispatch.py     dashboard.py
    ↑               ↑
telegram_sender  CLI (cli.py)
                    ↑
              api_server.py (Flask)
                    ↑
                   n8n (HTTP)
```

---

## Regras de Evolução

1. Antes de adicionar novo módulo: verificar se existe módulo relacionado
2. Novas tabelas: migrations incrementais, nunca DROP
3. Novos endpoints API: seguir padrão `/api/{recurso}/{acao}`
4. Novas páginas Streamlit: seguir padrão `N_NomePagina.py` em `pages/`
5. Novos campos em `articles`: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
6. Remoção de código: apenas com aprovação explícita
