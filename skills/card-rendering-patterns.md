# Skill — Padrões de Geração de Card (News Radar)

Referência para agentes implementando ou modificando geração de cards.

---

## Fluxo Atual

```
article (dados do banco)
    ↓
_render_html(article, template)  → substitui {{placeholders}}
    ↓
Playwright: browser.new_page(viewport 600×400)
    ↓
page.set_content(html, wait_until="networkidle")
    ↓
page.locator("#card").screenshot(path=card_path)
    ↓
Salva PNG em data/cards/card_{id[:16]}.png
    ↓
update_card_status(article_id, "pending", card_path)
```

---

## Template HTML

- Arquivo: `templates/card.html`
- Placeholders: `{{variavel}}` (não Jinja2 — substituição simples por string)
- Elemento raiz: `<div id="card">` — é este elemento que o Playwright captura
- CSS isolado — sem dependências de rede (sem Google Fonts externos, etc.)
- Viewport: 600×400px

---

## Placeholders Disponíveis

```
{{titulo}}           → article["title"]
{{editoria}}         → article.get("category") or "-"
{{prioridade}}       → label: CRITICA/ALTA/MEDIA/BAIXA/RUIDO
{{prioridade_cor}}   → hex: #dc2626 / #ea580c / #d97706 / #16a34a / #6b7280
{{resumo}}           → ai_json.resumo_curto ou summary[:200]
{{pontos_chave}}     → HTML <li> de ai_json.pontos_chave (máx 4)
{{fonte}}            → article["source"]
{{data}}             → published_at[:10]
{{score}}            → int(final_score)
{{ia_badge}}         → "IA" se ai_score existe, "AUTO" se não
{{localidade_tag}}   → <span class="tag local">localidade</span> ou ""
{{entidades_tags}}   → <span class="tag entidade">...</span> (máx 3)
{{conteudo_tag}}     → badge de riqueza do resumo
{{justificativa_html}} → div com justificativa_score ou ""
```

---

## Dados Mínimos Obrigatórios

Para gerar card sem erro:
- `articles.title` — obrigatório (sem fallback)
- `articles.source` — obrigatório (sem fallback)
- `articles.published_at` — fallback: string vazia
- `articles.priority` — fallback: "?" e cor neutra

Melhor qualidade com:
- `ai_json.resumo_curto` — mais preciso que summary bruto
- `ai_json.pontos_chave` — lista de bullets
- `ai_json.localidade`
- `ai_json.entidades` (máx 3 exibidos)
- `ai_json.justificativa_score`

---

## Implementação da Substituição de Template

```python
# card_renderer.py::_render_html() — padrão atual
return (
    template
    .replace("{{titulo}}", article.get("title") or "")
    .replace("{{editoria}}", article.get("category") or "-")
    .replace("{{prioridade}}", priority_label)
    .replace("{{prioridade_cor}}", priority_color)
    # ... todos os outros campos
)
```

Se migrar para Jinja2 no futuro:
```python
from jinja2 import Template
tmpl = Template(template_content)
html = tmpl.render(**context_dict)
```

---

## Playwright — Uso Correto

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 600, "height": 400})

    for article in articles:
        html = _render_html(article, template)
        card_path = CARDS_DIR / f"card_{article['id'][:16]}.png"

        page.set_content(html, wait_until="networkidle")
        page.locator("#card").screenshot(path=str(card_path))

        # Atualizar banco imediatamente após salvar
        update_card_status(article["id"], status="pending", card_path=str(card_path))

    browser.close()
```

---

## Não Bloquear Fluxo em Caso de Falha

```python
# dispatch.py::generate_card_for_dispatch()
try:
    cards = render_cards(scope=scope, limit=1, article_ids=[dispatch["article_id"]])
    card_path = cards[0]["card_path"] if cards else None
except Exception as e:
    error_msg = str(e)[:200]
    # NÃO propagar exceção — notificar e continuar
    _tg("sendMessage", json={"text": f"⚠️ Card não gerado: {error_msg}", ...})
    return {"ok": False, "error": error_msg}
```

---

## Templates Versionados (Futuro)

```
templates/
  card.html             → v1 atual (padrão)
  card_v2.html          → layout revisado
  card_breaking.html    → notícias urgentes
```

Ao criar novo template:
1. Copiar `card.html` como base
2. Renomear com versão
3. Manter todos os placeholders existentes (compatibilidade)
4. Registrar em tabela `card_templates` quando implementada

---

## Preview no Dashboard (Futuro)

```python
# Antes de gerar PNG, mostrar HTML no dashboard
html_content = _render_html(article, template)
st.components.v1.html(html_content, height=500, scrolling=True)

if st.button("Gerar PNG"):
    # Só gera PNG após confirmação
    cards = render_cards(article_ids=[article["id"]])
```

---

## Regeneração Segura

- Regenerar card não muda `editorial_status` do artigo
- Apenas atualiza `card_status = 'pending'` e `card_path`
- Novo PNG sobrescreve o anterior (mesmo caminho)
- Dispatch status volta para `article_approved` para reiniciar fluxo de aprovação de card

---

## O Que Evitar

- Não incluir fontes externas no CSS (Google Fonts, CDNs) — card fica sem estilo se offline
- Não gerar card de artigo sem title — resulta em card em branco
- Não deixar texto cortado visível — usar `overflow: hidden` e `text-overflow: ellipsis`
- Não usar `wait_until="load"` — usar `"networkidle"` para garantir renderização completa
