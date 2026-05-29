# Spec 09 — Geração de Card via Template HTML

**Status:** Funcional — documentar e evoluir
**Fase:** 7 (melhorias)

---

## Estado Atual

Geração de cards funciona em `card_renderer.py`. Template em `templates/card.html` com placeholders `{{variavel}}`. Playwright renderiza elemento `#card` e salva PNG em `data/cards/`.

---

## Fluxo Atual

```
1. Artigo aprovado no dispatch (approve_article)
2. dispatch.generate_card_for_dispatch(dispatch_id)
3. card_renderer.render_cards(scope, limit, article_ids)
4. Lê templates/card.html
5. _render_html(article, template) → substitui {{placeholders}}
6. Playwright: browser.new_page(viewport 600×400)
7. page.set_content(html, wait_until="networkidle")
8. page.locator("#card").screenshot(path=str(card_path))
9. Salva em data/cards/card_{id[:16]}.png
10. update_card_status(article_id, "pending", card_path)
```

---

## Placeholders do Template Atual

| Placeholder | Valor | Fonte |
|-------------|-------|-------|
| `{{titulo}}` | Título do artigo | articles.title |
| `{{editoria}}` | Categoria editorial | articles.category |
| `{{prioridade}}` | Label de prioridade | CRITICA/ALTA/MEDIA/BAIXA/RUIDO |
| `{{prioridade_cor}}` | Cor hex da prioridade | ranker mapping |
| `{{resumo}}` | Resumo curto | ai_json.resumo_curto ou articles.summary |
| `{{pontos_chave}}` | Lista HTML `<li>` | ai_json.pontos_chave (máx 4) |
| `{{fonte}}` | Nome da fonte | articles.source |
| `{{data}}` | Data formatada | articles.published_at[:10] |
| `{{score}}` | Score final | final_score_brasil/piaui/teresina |
| `{{ia_badge}}` | "IA" ou "AUTO" | se ai_score existe |
| `{{localidade_tag}}` | Tag de localidade | ai_json.localidade |
| `{{entidades_tags}}` | Tags de entidades | ai_json.entidades (máx 3) |
| `{{conteudo_tag}}` | Badge riqueza conteúdo | len(summary) |
| `{{justificativa_html}}` | Justificativa do score | ai_json.justificativa_score |

---

## Template HTML

**Estrutura do card (580×auto px):**
```
┌──────────────────────────────────────┐
│ HEADER: [PRIORIDADE] [editoria] [IA] │  ← cor dinâmica
├──────────────────────────────────────┤
│ TÍTULO DO ARTIGO                     │
│ resumo curto                         │
│ • ponto chave 1                      │
│ • ponto chave 2                      │
│ [local] [entidade] [conteudo]        │
│ justificativa do score               │
├──────────────────────────────────────┤
│ fonte · data          score ▓▓▓▓░ 72 │  ← footer
└──────────────────────────────────────┘
```

---

## Seleção de Artigos para Card

**Via dispatch (fluxo principal):**
```python
# dispatch.py
cards = render_cards(scope=scope, limit=1, article_ids=[dispatch["article_id"]])
```

**Via dashboard (manual):**
```python
# pages
cards = render_cards(scope=scope, limit=N)
# Usa: articles_pending_card() → priority IN ('alta','critica') AND card_status='none'
```

---

## Dados Mínimos Obrigatórios

Para gerar card sem erro:
- `articles.title` — obrigatório
- `articles.source` — obrigatório
- `articles.published_at` — fallback para "sem data"
- `articles.priority` — fallback para "?"

Ideais (melhoram qualidade):
- `ai_json.resumo_curto`
- `ai_json.pontos_chave`
- `ai_json.localidade`
- `ai_json.entidades`
- `ai_json.justificativa_score`

---

## Evolução Futura (Fase 7)

### Templates Versionados

```
templates/
  card.html          → atual (v1)
  card_v2.html       → novo layout
  card_breaking.html → template para urgentes
  card_investigacao.html → template investigativo
```

Tabela `card_templates` com campo `is_default` e `version`.

### Preview no Dashboard

Antes de aprovar o card, exibir:
- HTML renderizado via `st.components.v1.html()` ou imagem base64
- Botão "Gerar PNG" separado de "Aprovar"
- Possibilidade de editar título/resumo antes de gerar

### Regeneração Segura

```python
# Regenerar não muda editorial_status, só gera novo PNG
dispatch.regenerate_card(dispatch_id, user)
```

Novo PNG sobrescreve o anterior ou recebe sufixo de versão.

### Jinja2 (Futuro)

Migrar de `str.replace("{{var}}", value)` para Jinja2 para:
- Suporte a condicionais no template
- Formatação de datas diretamente no template
- Sanitização automática de valores

```python
# Futura implementação
from jinja2 import Template
tmpl = Template(html_content)
rendered = tmpl.render(**article_data)
```

---

## Dependência Playwright

Playwright é dependência crítica. Se falhar:
```python
try:
    cards = render_cards(...)
except Exception as e:
    # Não bloquear fluxo editorial
    # Logar erro
    # Notificar via dashboard
    # dispatch.status permanece article_approved para retry
```

Verificação de instalação:
```bash
playwright install chromium
playwright install-deps
```

---

## Critérios de Aceite

- [ ] Card gerado tem dimensão mínima 580px de largura
- [ ] Título não é cortado no card
- [ ] Prioridade exibida com cor correta
- [ ] PNG salvo em `data/cards/`
- [ ] `card_path` atualizado no banco
- [ ] Falha no Playwright não quebra dispatch — loga e notifica
- [ ] Card pode ser regenerado sem alterar status editorial
- [ ] Card com dados mínimos (sem IA) é gerado com fallbacks razoáveis
