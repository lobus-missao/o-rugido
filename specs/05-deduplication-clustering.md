# Spec 05 — Deduplicação e Agrupamento

**Status:** Parcial — deduplicação funcional, clustering a implementar
**Fase:** 5

---

## Deduplicação (Atual — Funcional)

### Nível 1: URL Exata

```sql
SELECT id FROM articles WHERE canonical_url = %s LIMIT 1
```

- Mais confiável
- `canonical_url` é UNIQUE no banco
- Remoção de UTMs e normalização garante que mesma notícia de fontes diferentes com URL similar seja deduplicada

### Nível 2: Title Signature (Fuzzy)

```sql
SELECT id FROM articles WHERE title_signature = %s LIMIT 1
```

- Hash de palavras do título normalizado
- Detecta quando mesma notícia é republicada com URL diferente (sindicalização)
- Risco: falso positivo para títulos curtos ou com poucas palavras relevantes
- Comportamento atual: se title_signature bate mas canonical_url difere → UPDATE do artigo existente

### Regra de Preferência

```python
# collector.py — preservar
cur.execute("SELECT id FROM articles WHERE canonical_url = %s LIMIT 1", ...)
if not existing:
    cur.execute("SELECT id FROM articles WHERE title_signature = %s LIMIT 1", ...)
```

URL tem prioridade absoluta. Title signature só é consultado se URL não bateu.

---

## Deduplicação Futura (Nível 3 — Fase 5)

### Similaridade Textual

Quando implementar: artigos com URLs diferentes mas conteúdo ≥85% similar.

Algoritmo proposto: TF-IDF com cosine similarity ou SimHash.

```python
# Hipótese de implementação futura
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def find_similar(text: str, candidates: list[str], threshold=0.85) -> str | None:
    if not candidates:
        return None
    vectorizer = TfidfVectorizer(max_features=500)
    matrix = vectorizer.fit_transform([text] + candidates)
    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    best_idx = scores.argmax()
    if scores[best_idx] >= threshold:
        return candidate_ids[best_idx]
    return None
```

**Ponto a validar:** custo computacional para 10k+ artigos. Pode requerer índice vetorial ou processamento em lote.

---

## Clustering por Assunto (Fase 5)

### Objetivo

Agrupar notícias que cobrem o mesmo evento ou tema em um único cluster. Permite:
- Ver quantas fontes cobriram um assunto
- Score agregado do cluster (mais fontes = mais relevante)
- Ranking por assunto, não apenas por notícia isolada
- Editor decide qual artigo representa o cluster

### Modelo de Dados

```sql
story_clusters (id, title, scope, article_count, source_count, cluster_score, status)
cluster_articles (cluster_id, article_id, is_primary, similarity_score)
```

### Algoritmo Proposto (Simples)

1. Pegar artigos das últimas 72h sem cluster
2. Para cada artigo: comparar title_signature + keywords com artigos existentes
3. Se similaridade ≥ threshold: adicionar ao cluster existente
4. Se nenhum cluster: criar novo cluster
5. Atualizar `cluster_score = avg(final_score) × log(article_count + 1)`

### Campos do Cluster

- `title` — título gerado automaticamente (do artigo mais relevante) ou manual
- `scope` — escopo do cluster (herdado da maioria dos artigos)
- `article_count` — número de artigos no cluster
- `source_count` — número de fontes distintas
- `cluster_score` — score agregado
- `status` — active | archived

### Score do Cluster

```python
# Hipótese de fórmula
cluster_score = avg(final_score_brasil) * log(source_count + 1) * recency_factor
```

Quanto mais fontes cobrindo o mesmo assunto, mais relevante o cluster.

### Dashboard de Clusters

- Listagem de clusters ativos por score
- Artigos agrupados por cluster com indicação do primário
- Ações: marcar artigo como primário, mesclar clusters, arquivar
- Filtros: scope, status, period

---

## Regras

1. Deduplicação por URL é inviolável — não criar duplicata de URL conhecida
2. Title signature é fuzzy — nunca remover artigo existente por colisão
3. Clustering não substitui deduplicação — são camadas independentes
4. Cluster pode ter artigos de fontes diferentes (mesmo evento, diversas coberturas)
5. `is_primary = TRUE` para o artigo que representa o cluster
6. Artigo pode pertencer a apenas um cluster por escopo

---

## Critérios de Aceite (Deduplicação)

- [ ] Dois artigos com a mesma canonical_url resultam em 1 registro
- [ ] Artigo republicado com URL diferente mas título idêntico resulta em UPDATE
- [ ] `raw_json` atualizado mesmo em caso de UPDATE
- [ ] `auto_score_*` recalculado no UPDATE se artigo sem ai_score

## Critérios de Aceite (Clustering — Fase 5)

- [ ] Artigos sobre o mesmo evento agrupados em um cluster
- [ ] `cluster_score` calculado corretamente
- [ ] Dashboard mostra clusters com contagem de fontes
- [ ] Editor pode marcar artigo primário do cluster
- [ ] Artigo rejeitado não influencia score do cluster
