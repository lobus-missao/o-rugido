# Skill — Padrões de Dashboard Streamlit (News Radar)

Referência para agentes implementando páginas Streamlit neste projeto.

---

## Estrutura Padrão de Página

```python
"""Descrição da página."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt
from news_radar.dashboard_queries import alguma_query

st.set_page_config(page_title="Titulo · News Radar", page_icon="🔣", layout="wide")
sidebar_controls()
st.title("🔣 Titulo da Página")

# === Filtros (SEMPRE no topo) ===
col1, col2, col3 = st.columns(3)
with col1:
    escopo = st.selectbox("Escopo", ["brasil", "piaui", "teresina"])

st.divider()

# === Conteúdo principal ===
try:
    dados = alguma_query(escopo=escopo)
except Exception as e:
    st.error(f"Erro: {e}")
    dados = []

# === Tabela ou lista ===
# ...
```

---

## Filtros

- Sempre no topo, antes do conteúdo
- Usar `st.columns()` para layout horizontal
- Defaults razoáveis (não filtros vazios por padrão)
- Persistir via `st.session_state` quando necessário para não resetar ao interagir

```python
# Persistência de filtro
if "scope" not in st.session_state:
    st.session_state.scope = "brasil"
scope = st.selectbox("Escopo", ["brasil", "piaui", "teresina"],
                     index=["brasil", "piaui", "teresina"].index(st.session_state.scope))
st.session_state.scope = scope
```

---

## Tabela de Dados

```python
import pandas as pd

if dados:
    df = pd.DataFrame(dados)
    df["published_at"] = df["published_at"].apply(lambda v: fmt_dt(v, 16))
    st.dataframe(df, use_container_width=True, height=400)
else:
    st.info("Nenhum dado encontrado.")
```

---

## Painel Lateral de Detalhes

```python
# Usar expander para detalhes inline
for item in items:
    with st.expander(f"📰 {item['title'][:80]}"):
        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.markdown(f"**Fonte:** {item['source']}")
            st.markdown(f"**Resumo:** {item.get('summary', '')[:200]}")
        with col_b:
            # Ações
            if st.button("✅ Aprovar", key=f"aprovar_{item['id']}"):
                ...
```

---

## Ações Explícitas

```python
# Botões com rótulos completos
if st.button("▶ Coletar feeds", use_container_width=True):
    with st.spinner("Coletando feeds..."):
        r = run_cli("collect", "--limit-per-feed", "30", timeout=180)
    if r["ok"]:
        st.success(f"✅ {r.get('inserted', 0)} inseridos")
    else:
        st.error(r.get("error", "Erro desconhecido"))
```

---

## Confirmação para Ações Destrutivas

```python
# Confirmar antes de ações irreversíveis
if st.button("❌ Rejeitar artigo", type="secondary"):
    st.session_state[f"confirmar_rejeitar_{dispatch_id}"] = True

if st.session_state.get(f"confirmar_rejeitar_{dispatch_id}"):
    st.warning("⚠️ Confirme a rejeição:")
    col_sim, col_nao = st.columns(2)
    with col_sim:
        if st.button("Sim, rejeitar", type="primary", key=f"sim_{dispatch_id}"):
            result = dispatch.reject_article(dispatch_id, user="Editor")
            st.success("Artigo rejeitado.")
            del st.session_state[f"confirmar_rejeitar_{dispatch_id}"]
    with col_nao:
        if st.button("Cancelar", key=f"nao_{dispatch_id}"):
            del st.session_state[f"confirmar_rejeitar_{dispatch_id}"]
```

---

## Feedback Visual

```python
# Sempre dar feedback ao usuário
with st.spinner("Processando..."):
    resultado = fazer_operacao()

if resultado.get("ok"):
    st.success("✅ Operação concluída!")
    st.rerun()  # Atualizar a página após sucesso
else:
    st.error(f"❌ {resultado.get('error', 'Erro desconhecido')}")
```

---

## Status com Cores

```python
# dash_utils.py — usar funções existentes
from news_radar.dash_utils import PRIORITY_COLOR, PRIORITY_ICON

icon = PRIORITY_ICON.get(priority, "⚪")
color = PRIORITY_COLOR.get(priority, "#6b7280")
```

---

## run_cli — Chamar Comandos

```python
# dash_utils.py::run_cli() — wrapper do CLI
from news_radar.dash_utils import run_cli

r = run_cli("collect", "--limit-per-feed", "30", timeout=180)
# Retorna: {"ok": True/False, ...dados...} ou {"ok": False, "error": "..."}
```

---

## Organização por Páginas

```
dashboard.py          → página principal (Radar)
pages/0_Edicoes.py    → controle de edições
pages/1_Operacao.py   → saúde do pipeline
pages/2_Lotes_IA.py   → lotes de IA
...
```

Numerar as páginas para ordenação. Ordem visível no sidebar.

---

## O Que Evitar

- Não colocar queries SQL diretamente no arquivo da página
- Não usar `time.sleep()` — usar spinner
- Não deixar exceções sem tratamento — sempre `try/except`
- Não usar `st.rerun()` em loop — só após ação do usuário
- Não carregar dados em loop sem paginação (usar `LIMIT`)
- Não hardcodar textos de erro — usar variáveis descritivas
