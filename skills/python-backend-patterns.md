# Skill — Padrões de Backend Python (News Radar)

Referência para agentes implementando código Python neste projeto.

---

## Organização de Módulos (`src/news_radar/`)

| Módulo | Responsabilidade |
|--------|-----------------|
| `config.py` | Paths, variáveis de ambiente, ensure_dirs() |
| `db.py` | Schema, connect(), init_db(), json_dumps/loads |
| `collector.py` | RSS → normalize → upsert |
| `ranker.py` | Fórmulas de score |
| `repository.py` | Queries de leitura reutilizáveis |
| `ai_batches.py` | make_batches, import_result |
| `card_renderer.py` | HTML → Playwright → PNG |
| `dispatch.py` | Fluxo editorial e Telegram |
| `cli.py` | Comandos argparse |
| `dash_utils.py` | Componentes Streamlit |
| `dashboard_queries.py` | Queries específicas da dashboard |

---

## Padrão de Conexão ao Banco

```python
# Sempre usar o context manager
from .db import connect

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
        row = cur.fetchone()
# commit automático ao sair do with sem exceção
# rollback automático em exceção
```

---

## Padrão de Serviço (Use Case)

Funções de negócio em módulos dedicados, não no arquivo da página:

```python
# BAD — lógica no arquivo da página
def on_click():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE articles SET ...")

# GOOD — chamar módulo
from news_radar.dispatch import approve_article
result = approve_article(dispatch_id, user)
```

---

## Padrão de Repository

```python
# repository.py — queries de leitura reutilizáveis
def top_articles(scope, limit, days_back=None, search=None, priority=None) -> list[dict]:
    ...
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
```

Não colocar queries complexas diretamente nos arquivos de página.

---

## Schemas e Validação

Sem ORM — usar validação explícita:

```python
def validate_ai_item(item: dict) -> tuple[bool, str]:
    if not item.get("id"):
        return False, "id ausente"
    return True, ""
```

---

## Logging

```python
import traceback

try:
    resultado = fazer_algo()
except Exception as exc:
    error = f"{exc}\n{traceback.format_exc(limit=2)}"
    # Registrar no banco quando possível
    # Nunca silenciar exceções sem log
```

---

## Tratamento de Erro

- Não silenciar exceções com `except: pass`
- Logar mensagem + traceback (truncado)
- Em jobs de coleta: registrar erro em `feed_runs`, continuar próxima fonte
- Em importação de IA: registrar item com status "erro", continuar próximo

---

## JSON Seguro

```python
# db.py — funções utilitárias
def json_dumps(value) -> str | None:
    if value is None: return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def json_loads(value, default=None):
    if not value: return default
    if isinstance(value, (dict, list)): return value
    try: return json.loads(value)
    except Exception: return default
```

---

## Separação de Regra de Negócio

```
CLI (cli.py)          → interface de linha de comando, sem lógica
API Flask             → interface HTTP, sem lógica
Dashboard pages       → interface visual, sem lógica pesada
↓
Módulos Python        → TODA a regra de negócio
  collector.py, ranker.py, ai_batches.py, dispatch.py, card_renderer.py
↓
db.py / repository.py → acesso ao banco
```

---

## Compatibilidade com o Projeto Atual

1. Novas funções em módulos existentes: verificar se já existe função similar
2. Novos módulos: registrar em `__init__.py` se necessário para imports
3. Novas tabelas: adicionar à `SCHEMA_SQL` ou `MIGRATION_SQL` em `db.py`
4. Novos campos em articles: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` em `MIGRATION_SQL`
5. Novos comandos CLI: adicionar ao `build_parser()` em `cli.py`
6. Novos endpoints: adicionar ao `api_server.py`
