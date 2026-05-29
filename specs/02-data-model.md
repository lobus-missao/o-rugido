# Spec 02 — Modelo de Dados Editorial

**Status:** Aprovado
**Fase:** 0 — Diagnóstico e SDD

---

## Tabelas Existentes (Preservar)

### `articles` — Tabela Central

Contém todo o ciclo de vida de um artigo: captura → normalização → ranking → IA → editorial → card.

```sql
articles (
    id TEXT PK,                        -- hash(canonical_url + title)
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,              -- nome da fonte
    source_scope TEXT NOT NULL,        -- 'brasil' | 'piaui' | 'teresina'
    source_trust NUMERIC DEFAULT 0.5,  -- 0.0 a 1.0

    published_at TIMESTAMPTZ,
    summary TEXT,
    content TEXT,
    title_signature TEXT,              -- hash fuzzy para dedup por título
    raw_json JSONB,                    -- entrada bruta preservada

    -- Scores automáticos (por termos/regras)
    auto_score_brasil NUMERIC DEFAULT 0,
    auto_score_piaui NUMERIC DEFAULT 0,
    auto_score_teresina NUMERIC DEFAULT 0,

    -- Scores finais (auto × 0.58 + ai × 0.42)
    final_score_brasil NUMERIC DEFAULT 0,
    final_score_piaui NUMERIC DEFAULT 0,
    final_score_teresina NUMERIC DEFAULT 0,

    -- Dados da IA
    ai_score NUMERIC,
    ai_json JSONB,                     -- resposta completa da IA
    category TEXT,                     -- editoria inferida pela IA
    locality TEXT,
    priority TEXT,                     -- 'ruido' | 'baixa' | 'media' | 'alta' | 'critica'
    entities_json JSONB,
    score_reasons_json JSONB,          -- razões do score automático

    -- Status do card
    card_status TEXT DEFAULT 'none',   -- none | pending | approved | rejected
    card_path TEXT,

    -- Status editorial
    editorial_status TEXT DEFAULT 'discovered',
    -- discovered | needs_ai | ai_done | selected |
    -- sent_to_telegram | approved | rejected | ready_to_publish | published | archived | card_rejected

    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
)
```

**Índices existentes:**
- UNIQUE em `canonical_url`
- em `title_signature`, `published_at`, `final_score_*`, `source_scope`, `card_status`, `editorial_status`

### `feed_runs` — Log de Coletas

```sql
feed_runs (
    id SERIAL PK,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'ok' | 'warning' | 'error'
    collected_count INTEGER DEFAULT 0,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL
)
```

### `ai_batches` — Controle de Lotes de IA

```sql
ai_batches (
    batch_id TEXT PK,              -- ex: batch_brasil_20260526_203218_part01
    scope TEXT NOT NULL,           -- 'brasil' | 'piaui' | 'teresina'
    status TEXT NOT NULL,          -- pending | running | completed | failed | expired
    model TEXT,                    -- modelo IA usado (se aplicável)
    article_count INTEGER DEFAULT 0,
    prompt_path TEXT NOT NULL,     -- path do .prompt.txt gerado
    payload_path TEXT NOT NULL,    -- path do .json com artigos compactos
    result_path TEXT,              -- path do .result.json importado
    imported_count INTEGER DEFAULT 0,
    ignored_count INTEGER DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
)
```

### `dispatches` — Fluxo Editorial de Edições

```sql
dispatches (
    id SERIAL PK,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    edition TEXT NOT NULL,         -- 'morning' | 'noon' | 'evening'
    edition_date DATE NOT NULL,
    rank INTEGER NOT NULL,         -- posição na edição (1, 2, 3)
    scope TEXT DEFAULT 'brasil',
    status TEXT DEFAULT 'pending_article',
    -- pending_article | article_approved | article_rejected |
    -- pending_card | card_rejected | ready_to_publish | published

    article_tg_message_id TEXT,    -- ID da mensagem Telegram do artigo
    card_tg_message_id TEXT,       -- ID da mensagem Telegram do card
    card_path TEXT,

    article_reviewed_by TEXT,
    article_reviewed_at TIMESTAMPTZ,
    card_reviewed_by TEXT,
    card_reviewed_at TIMESTAMPTZ,
    ready_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

---

## Tabelas a Adicionar (Fase 2+)

### `sources` — Fontes Gerenciáveis (substitui feeds.yaml gradualmente)

```sql
sources (
    id SERIAL PK,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    source_type TEXT DEFAULT 'rss',    -- 'rss' | 'api' | 'scraping' | 'manual'
    scope TEXT NOT NULL DEFAULT 'brasil',
    trust NUMERIC DEFAULT 0.5,
    enabled BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

**Estratégia de migração:** adicionar tabela, importar feeds.yaml para ela, manter leitura do YAML como fallback durante transição.

### `editorial_actions` — Auditoria de Ações Editoriais

```sql
editorial_actions (
    id SERIAL PK,
    article_id TEXT REFERENCES articles(id),
    dispatch_id INTEGER REFERENCES dispatches(id),
    action TEXT NOT NULL,          -- 'approve' | 'reject' | 'ai_import' | 'card_generate' | ...
    actor TEXT NOT NULL DEFAULT 'system',
    from_status TEXT,
    to_status TEXT,
    notes TEXT,
    metadata JSONB,                -- dados extras da ação
    created_at TIMESTAMPTZ DEFAULT NOW()
)
```

### `story_clusters` — Grupos de Notícias por Assunto (Fase 5)

```sql
story_clusters (
    id TEXT PK,                    -- hash do assunto principal
    title TEXT NOT NULL,           -- título do cluster (gerado ou manual)
    scope TEXT NOT NULL DEFAULT 'brasil',
    article_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,
    cluster_score NUMERIC DEFAULT 0,
    status TEXT DEFAULT 'active',  -- active | archived
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### `cluster_articles` — Artigos em Clusters

```sql
cluster_articles (
    cluster_id TEXT REFERENCES story_clusters(id),
    article_id TEXT REFERENCES articles(id),
    is_primary BOOLEAN DEFAULT FALSE,
    similarity_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cluster_id, article_id)
)
```

### `articles` — Campos Futuros (a adicionar incrementalmente)

```sql
-- Suporte a rollback de importação IA (Fase 4+)
editor_score_override NUMERIC,           -- override manual do editor
editor_score_reason TEXT,
editor_score_by TEXT,
editor_score_at TIMESTAMPTZ,
ai_import_version INTEGER DEFAULT 0,     -- contador de importações IA (para rollback)
ai_import_previous_json JSONB,           -- backup do ai_json antes da última importação
```

### `card_templates` — Templates Versionados (Fase 7)

```sql
card_templates (
    id SERIAL PK,
    name TEXT NOT NULL UNIQUE,     -- ex: 'card_v1', 'card_breaking'
    description TEXT,
    html_path TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    version TEXT DEFAULT '1.0',
    created_at TIMESTAMPTZ DEFAULT NOW()
)
```

### `score_weights` — Pesos Configuráveis do Ranking (Fase 6)

```sql
score_weights (
    id SERIAL PK,
    scope TEXT NOT NULL DEFAULT 'brasil',
    dimension TEXT NOT NULL,       -- ex: 'public_org', 'risk', 'money_public'
    weight NUMERIC NOT NULL DEFAULT 1.0,
    max_contribution NUMERIC,
    updated_by TEXT DEFAULT 'system',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (scope, dimension)
)
```

---

## Regras do Modelo

1. **Nunca remover colunas** da tabela `articles` sem migration de compatibilidade
2. **`raw_json`** é **sempre atualizado** para refletir o dado mais recente do feed — não remover esta coluna nem adicionar proteção que bloqueie seu UPDATE. O `collector.py` atualiza `raw_json` a cada coleta do mesmo artigo (`upsert_article()`, linha ~98).
3. **`ai_json`** é JSONB livre — validar antes de importar, nunca confiar cegamente
4. **`editorial_status`** é a fonte de verdade do estado do artigo. **Atenção:** o estado `'approved'` não é escrito pelo fluxo de dispatch atual (`dispatch.approve_article()` atualiza `dispatches.status`, não `articles.editorial_status`). O estado `'approved'` existe no enum por compatibilidade histórica (migration) e para uso manual futuro. Ver spec/10 para detalhes.
5. **`final_score_*`** é o score usado para ordenação — sempre atualizado em `rank`
6. **`canonical_url`** é a chave de deduplicação primária
7. **`title_signature`** é auxiliar — colisão possível, nunca sobrescreve via `canonical_url`
8. **Migrations** são `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — nunca destrutivas
9. **JSONB** preferível a múltiplas colunas para dados que crescem com o tempo

---

## Mapeamento: Spec → Projeto Real

| Termo da spec | Nome real no banco | Tabela |
|---------------|-------------------|--------|
| source | source + source_scope | articles |
| collection_job | feed_runs | feed_runs |
| raw_article | articles (raw_json) | articles |
| normalized_article | articles (campos normalizados) | articles |
| article_score | auto_score_* + final_score_* + ai_score | articles |
| ai_batch | ai_batches | ai_batches |
| ai_import | (dentro de ai_batches) | ai_batches |
| editorial_status_history | editorial_actions (a criar) | — |
| card_template | card_templates (a criar) | — |
| generated_card | card_path + card_status | articles |
| approval_event | dispatches | dispatches |
| story_cluster | story_clusters (a criar) | — |
