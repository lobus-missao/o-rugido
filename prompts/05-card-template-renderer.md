# Prompt 05 — Geração de Cards via HTML/PNG (Fase 7)

---

## Contexto

A geração de cards já funciona via `card_renderer.py` + `templates/card.html` + Playwright. O objetivo desta fase é melhorar a experiência: preview antes de aprovar, templates versionados, e melhor integração com a dashboard.

---

## Spec de Referência

Leia: `specs/09-card-template-renderer.md`

---

## O Que Implementar

### 1. Preview de Card na Dashboard

Na página `0_Edicoes.py`, ao exibir dispatch com card aprovado:

```python
dispatch = get_dispatch(dispatch_id)
if dispatch.get("card_path") and Path(dispatch["card_path"]).exists():
    st.image(dispatch["card_path"], caption="Card gerado", use_column_width=False, width=400)
```

### 2. Gerar Card Diretamente pelo Dashboard

Na mesa editorial (`5_Editorial.py`):

```python
if st.button("🖼️ Gerar card", key=f"card_{article_id}"):
    with st.spinner("Gerando card..."):
        r = run_cli("make-card", "--scope", scope, "--limit", "1")
    if r["ok"]:
        st.success("Card gerado!")
    else:
        st.error(f"Erro: {r.get('error')}")
```

### 3. Regenerar Card com Feedback

Já existe via `dispatch.regenerate_card()`. Verificar que o feedback no dashboard está claro.

### 4. Verificar Instalação do Playwright

Na página de Operação, exibir alerta se Playwright não está instalado:

```python
try:
    from playwright.sync_api import sync_playwright
    playwright_ok = True
except ImportError:
    playwright_ok = False

if not playwright_ok:
    st.warning("⚠️ Playwright não instalado. Geração de cards indisponível.")
    st.code("playwright install chromium")
```

---

## Regras

1. Não alterar `card_renderer.py` sem necessidade
2. Não alterar `templates/card.html` sem justificativa visual
3. Falha no Playwright não deve crashar o dashboard
4. Preview é apenas `st.image()` do PNG já gerado
5. Não gerar PNG sem artigo selecionado

---

## Verificação Manual do Template

```python
# Verificar que template renderiza corretamente
from src.news_radar.card_renderer import _render_html
from pathlib import Path

template = Path("templates/card.html").read_text(encoding="utf-8")
article = {
    "title": "Teresina abre licitação de ônibus",
    "source": "Cidade Verde",
    "published_at": "2026-05-29",
    "priority": "alta",
    "category": "Governos e politica",
    "ai_json": {
        "resumo_curto": "Contrato de R$12mi com indício de sobrepreço",
        "pontos_chave": ["R$12 milhões", "40% acima do mercado"],
        "localidade": "Teresina",
        "entidades": ["STRANS", "Câmara Municipal"],
        "justificativa_score": "Alto risco investigativo"
    },
    "final_score_piaui": 78.5,
    "ai_score": 8.2,
}

html = _render_html(article, template)
print(html[:500])  # verificar que placeholders foram substituídos
```

---

## Critérios de Aceite

- [ ] Preview de card visível na página de Edições
- [ ] Botão "Gerar card" funciona na mesa editorial
- [ ] Falha no Playwright exibe aviso claro, não crash
- [ ] Card PNG tem dimensão correta (≥580px largura)
- [ ] Título nunca cortado no card
- [ ] Card com dados mínimos (sem IA) ainda gerado
