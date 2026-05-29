# Skill — Padrões de Banco de Dados (News Radar)

Referência para agentes fazendo alterações no banco PostgreSQL.

---

## Regra Fundamental

**O banco é a fonte de verdade. Nunca apague dados sem aprovação explícita.**

---

## Migrations Incrementais

Toda mudança de schema vai em `MIGRATION_SQL` em `db.py`:

```python
MIGRATION_SQL = [
    # Padrão correto — incremental, seguro
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS novo_campo TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS outro_campo NUMERIC DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_articles_novo_campo ON articles(novo_campo)",
]
```

**Nunca usar:**
```sql
-- PROIBIDO sem aprovação
DROP COLUMN novo_campo;
DROP TABLE articles;
ALTER TABLE articles ALTER COLUMN campo TYPE TEXT;  -- só se não quebrar dados existentes
```

---

## Criar Nova Tabela

```python
SCHEMA_SQL = [
    # ... tabelas existentes ...
    """
    CREATE TABLE IF NOT EXISTS nova_tabela (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        descricao TEXT,
        status TEXT NOT NULL DEFAULT 'ativo',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_nova_tabela_status ON nova_tabela(status)",
]
```

---

## Preservar Raw Data

- `raw_json` em `articles` é imutável — nunca sobrescrever em UPDATE sem motivo
- Para scraping: salvar HTML bruto em campo separado ou arquivo referenciado no banco
- JSONB para dados que podem crescer sem alterar schema

---

## Índices Obrigatórios

| Caso | Índice |
|------|--------|
| Deduplicação por URL | `UNIQUE ON articles(canonical_url)` ✅ |
| Dedup fuzzy | `ON articles(title_signature)` ✅ |
| Ranking por score | `ON articles(final_score_brasil DESC)` ✅ |
| Filtro por data | `ON articles(published_at)` ✅ |
| Filtro por status editorial | `ON articles(editorial_status)` ✅ |
| Filtro por escopo | `ON articles(source_scope)` ✅ |
| Log de coletas | `ON feed_runs(source, started_at)` (futuro) |
| Auditoria por artigo | `ON editorial_actions(article_id)` (futuro) |

---

## JSONB

Usar quando o dado é semi-estruturado ou pode crescer:

```sql
-- Campos JSONB existentes
articles.raw_json         -- entrada bruta do RSS
articles.ai_json          -- resposta completa da IA
articles.entities_json    -- lista de entidades
articles.score_reasons_json -- lista de razões do score
```

Consultar JSONB:
```sql
SELECT ai_json->>'resumo_curto' FROM articles WHERE ai_score IS NOT NULL;
SELECT ai_json->'entidades' FROM articles WHERE id = 'xxx';
```

---

## Histórico de Status

Futuro: tabela `editorial_actions` para rastrear toda mudança de status:

```sql
-- Ao invés de só atualizar editorial_status em articles:
UPDATE articles SET editorial_status = 'approved' WHERE id = %s;

-- Também registrar:
INSERT INTO editorial_actions (article_id, action, actor, from_status, to_status)
VALUES (%s, 'approve_article', %s, %s, 'approved');
```

---

## Auditoria Básica (Disponível Agora)

Campos já existentes em `dispatches`:
```sql
article_reviewed_by TEXT  -- quem aprovou o artigo
article_reviewed_at TIMESTAMPTZ
card_reviewed_by TEXT
card_reviewed_at TIMESTAMPTZ
```

---

## Datas

- Todas as colunas de data: `TIMESTAMPTZ`
- Inserir sempre em UTC: `utc_now()` de `db.py`
- Converter ao exibir no dashboard: `fmt_dt()` de `dash_utils.py`
- Migration existente: `_ensure_datetime_columns()` já converte para TIMESTAMPTZ

---

## Compatibilidade com Banco Atual

Ao adicionar nova tabela com FK para `articles`:
```sql
REFERENCES articles(id) ON DELETE CASCADE
-- ou
REFERENCES articles(id) ON DELETE SET NULL
```

Verificar qual comportamento é correto para o contexto.

---

## Não Usar ORM

O projeto usa psycopg2 direto. Não introduzir SQLAlchemy, Tortoise, etc. sem aprovação.

```python
# Padrão correto
with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...", params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
```

---

## Backup (Lembrete)

```bash
# Backup manual do banco
pg_dump news_radar > backup_YYYYMMDD.sql

# Restore
psql news_radar < backup_YYYYMMDD.sql
```

Configurar backup automático antes de ir para produção com dados reais.
