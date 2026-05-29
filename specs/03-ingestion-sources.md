# Spec 03 — Fontes e Ingestão

**Status:** Aprovado
**Fase:** 3 (fontes gerenciáveis) / Funcional atual para RSS

---

## Estado Atual

RSS via feedparser funciona. 57 feeds configurados em `configs/feeds.yaml`. Coleta chama `collector.collect_feeds()`. Log em `feed_runs`.

---

## Tipos de Fonte

### 1. RSS (atual — funcional)
- **Quando usar:** fonte tem feed RSS público
- **Biblioteca:** feedparser
- **Configuração:** `configs/feeds.yaml` (name, url, scope, trust, enabled)
- **Preservar:** comportamento atual de `collector.py` intacto

### 2. API Pública/Gratuita (futuro — Fase 3)
- **Quando usar:** fonte oferece API REST sem autenticação ou com chave gratuita
- **Exemplos:** Google News API, NewsAPI.org (free tier), Portal da Transparência
- **Biblioteca:** requests + adaptador específico
- **Padrão:** retornar dicionário compatível com `normalize_entry()`

### 3. Scraping Simples (futuro — Fase 3)
- **Quando usar:** fonte não tem RSS, mas HTML é simples/estático
- **Biblioteca:** requests + BeautifulSoup + trafilatura (extração de texto)
- **Limite:** não usar para sites com captcha, paywall, ou JS pesado

### 4. Scraping com Browser (futuro — Fase 3)
- **Quando usar:** conteúdo carregado via JavaScript
- **Biblioteca:** Playwright (já instalado para cards)
- **Custo:** alto — usar como último recurso
- **Limite:** máximo 5 fontes com Playwright simultâneas

### 5. Importação Manual (futuro — Fase 8)
- **Quando usar:** notícia importante sem cobertura automática
- **Interface:** dashboard > aba Fontes > Adicionar manual
- **Campos obrigatórios:** title, url, source, scope
- **Status:** `editorial_status = 'selected'` ao importar manualmente

---

## Configuração de Fonte

Atualmente em `feeds.yaml`. Migrar gradualmente para tabela `sources`:

```yaml
# Formato atual (preservar compatibilidade)
feeds:
- name: G1
  url: https://g1.globo.com/rss/g1/
  scope: brasil
  trust: 0.85
  enabled: true
```

```sql
-- Formato alvo (tabela sources)
INSERT INTO sources (name, url, source_type, scope, trust, enabled)
VALUES ('G1', 'https://g1.globo.com/rss/g1/', 'rss', 'brasil', 0.85, true);
```

**Estratégia de transição:** `load_feeds_config()` lê YAML → banco como segunda opção → banco como primário quando implementado.

---

## Ciclo de Coleta

```
1. Carregar lista de fontes ativas (YAML ou banco)
2. Para cada fonte:
   a. Registrar started_at em feed_runs
   b. Tentar buscar com timeout configurado
   c. Em caso de erro: status='error', logar, continuar próxima fonte
   d. Para cada entrada: normalize_entry() → upsert_article()
   e. Registrar finished_at, collected_count, status em feed_runs
3. Retornar resumo: inserted, updated, errors
```

---

## Idempotência e Deduplicação

1. **Dedup primário:** `canonical_url` — UNIQUE no banco
2. **Dedup secundário:** `title_signature` — hash de palavras do título normalizado
3. **Comportamento em colisão:** UPDATE dos campos (não INSERT duplicado)
4. **`raw_json`:** atualizado mesmo em UPDATE para manter dado mais recente
5. **Scores:** recalculados no UPDATE apenas se `ai_score IS NULL`

```python
# Lógica atual em collector.py — preservar
cur.execute("SELECT id FROM articles WHERE canonical_url = %s LIMIT 1", ...)
if not existing:
    cur.execute("SELECT id FROM articles WHERE title_signature = %s LIMIT 1", ...)
```

---

## Rate Limiting e Retry

Estado atual: sem retry automático. Adição futura:

```python
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]  # segundos

for attempt in range(MAX_RETRIES):
    try:
        parsed = feedparser.parse(source["url"], ...)
        break
    except Exception:
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[attempt])
        else:
            status = "error"; error = str(exc)
```

Rate limit por fonte: no mínimo 1 segundo entre requisições da mesma fonte.

---

## Preservação de Dado Bruto

- `raw_json` JSONB — entrada bruta do RSS sempre salva
- Para scraping: salvar `raw_html` ou `raw_text` em campo futuro ou arquivo
- Dado bruto nunca é removido por normalização

---

## Status por Fonte

Monitorável via `feed_runs`:

```sql
SELECT source, status, collected_count, error, finished_at
FROM feed_runs
ORDER BY id DESC
LIMIT 100;
```

Futuro: tabela `sources` com `last_run_at`, `last_status`, `error_count` atualizados após cada coleta.

---

## Logs de Erro

- Erro registrado em `feed_runs.error` (max 500 chars)
- Erro não interrompe coleta das demais fontes
- Dashboard > Operação exibe erros das últimas 24h
- Alerta quando fonte tem ≥3 erros consecutivos (futuro)

---

## Critérios de Aceite

- [ ] Coletar 57 feeds sem parar em caso de erro em um deles
- [ ] `feed_runs` registrado para cada fonte, com ou sem erro
- [ ] Artigo duplicado (mesma canonical_url) resulta em UPDATE, não INSERT
- [ ] `raw_json` preservado após normalização
- [ ] Dashboard > Operação mostra log de coletas em tempo real
