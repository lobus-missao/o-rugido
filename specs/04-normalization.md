# Spec 04 — Normalização

**Status:** Aprovado
**Fase:** 0 — Funcional atual

---

## Estado Atual

Normalização acontece em `collector.py::normalize_entry()` e `text_utils.py`. Funciona para RSS. Esta spec documenta o comportamento existente e o alvo.

---

## Pipeline de Normalização Atual

```python
# collector.py::normalize_entry()
title = strip_html(entry.title)           # remove HTML do título
url = entry.link
canonical_url = canonicalize_url(url)    # remove UTMs, fragmentos, trailing /
summary = strip_html(entry.summary)       # remove HTML do resumo
published_at = entry_published_at(entry) # parse de data com fallback
title_signature = title_signature(title)  # hash normalizado para dedup
raw_json = dict(entry)                    # dado bruto preservado
```

---

## Funções de Normalização (`text_utils.py`)

### `canonicalize_url(url)`
Objetivo: gerar URL canônica para deduplicação
- Remove parâmetros UTM (`utm_source`, `utm_medium`, etc.)
- Remove fragmento `#`
- Remove `trailing /`
- Normaliza scheme para `https` quando possível
- Resultado é a chave de deduplicação primária

### `title_signature(title)`
Objetivo: hash fuzzy para detectar títulos similares
- Normaliza texto (remove acentos, lowercase, strip)
- Remove stopwords comuns
- Gera hash MD5 das palavras restantes
- Colisão possível entre títulos muito diferentes — não é chave primária

### `strip_html(text)`
- Remove tags HTML
- Decodifica entidades HTML
- Remove espaços extras
- Usado em: title, summary, content

### `normalize_text(text)` / `normalize_spaces(text)`
- Remove espaços duplos, tabs, newlines excessivos
- Usado na geração de prompts para IA

---

## Campos Preenchidos na Normalização

| Campo | Fonte | Obrigatório |
|-------|-------|-------------|
| id | hash(canonical_url + title) | Sim |
| title | entry.title (strip_html) | Sim |
| url | entry.link | Sim |
| canonical_url | canonicalize_url(url) | Sim |
| source | feeds.yaml[name] | Sim |
| source_scope | feeds.yaml[scope] | Sim |
| source_trust | feeds.yaml[trust] | Sim |
| published_at | parse(entry.published/updated/created) | Não |
| summary | entry.summary ou description (strip_html) | Não |
| content | mesmo que summary por ora | Não |
| title_signature | title_signature(title) | Sim |
| raw_json | dict(entry) | Sim |

---

## Campos Deixados para IA

Preenchidos apenas após importação de lote:

| Campo | Fonte |
|-------|-------|
| category / editoria | IA |
| locality | IA |
| priority | IA |
| entities_json | IA |
| ai_json (completo) | IA |
| ai_score | calculado a partir de ai_json |

---

## Padronização de Data

Ordem de tentativa:
1. `entry.published`
2. `entry.updated`
3. `entry.created`

Para cada: `dateutil.parser.parse(value).astimezone(timezone.utc)`

Se nenhuma data disponível: `published_at = NULL`

Colunas de data: `TIMESTAMPTZ` após migration existente.

---

## Localidade e Escopo

- `source_scope` vem do YAML (`brasil`, `piaui`, `teresina`)
- `locality` vem da IA (campo livre: cidade, estado ou "Nacional")
- Não há geocodificação automática nesta fase

---

## Extração de Entidades

- `entities_json` vem da IA — lista de strings
- Não há extração automática por NER nesta fase
- Página `6_Entidades.py` exibe entidades importadas pela IA

---

## Tags e Categorias

- `category` = editoria retornada pela IA
- Valores esperados: "Governos e politica", "Contas publicas", "Justica e controle", "Saude", "Educacao", "Seguranca", "Infraestrutura", "Cidades", "Economia", "Esporte", "Cultura", "Outros"
- Sem tags adicionais nesta fase

---

## Status de Normalização

Atual: implícito — se o artigo está no banco, foi normalizado.
Futuro: campo `normalization_status` para detectar artigos com normalização parcial.

---

## Critérios de Aceite

- [ ] `title` e `canonical_url` sempre preenchidos (entrada rejeitada se vazios)
- [ ] `raw_json` sempre preservado
- [ ] Data sempre em UTC (TIMESTAMPTZ)
- [ ] Artigo com mesmo `canonical_url` não gera duplicata
- [ ] `strip_html` não deixa tags HTML visíveis no título ou resumo
