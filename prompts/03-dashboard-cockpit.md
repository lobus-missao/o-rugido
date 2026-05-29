# Prompt 03 — Fortalecer Dashboard como Cockpit (Fase 3)

---

## Contexto

A dashboard Streamlit já existe em `dashboard.py` + `pages/`. Várias páginas estão funcionais. O objetivo desta fase é garantir que o editor consiga operar o ciclo completo sem abrir terminal ou n8n.

---

## Spec de Referência

Leia: `specs/08-editorial-dashboard.md`

---

## Prioridade de Melhorias

### Alta Prioridade

1. **Gerenciamento de fontes (`8_Fontes_RSS.py`):**
   - Listar fontes com status (ativa, erro recente, desabilitada)
   - Habilitar/desabilitar fonte pelo dashboard
   - Exibir última coleta e contagem por fonte
   - Sem quebrar `feeds.yaml` (leitura existente deve continuar)

2. **Ações diretas pela mesa editorial (`5_Editorial.py`):**
   - Botão "Gerar card" por artigo sem abrir Edições
   - Botão "Marcar como needs_ai" para enviar para lote
   - Filtro por `editorial_status` funcional

3. **Status do scheduler (`1_Operacao.py`):**
   - Exibir se scheduler interno está ativo ou não
   - Exibir próxima execução de coleta
   - Botão "Forçar coleta agora" (já existe, verificar funcionamento)

### Média Prioridade

4. **Preview básico do card antes de aprovar (`0_Edicoes.py`):**
   - Exibir imagem do card quando `card_path` existe
   - Usar `st.image(card_path)`

5. **Validação e feedback na importação IA (`2_Lotes_IA.py`):**
   - Já existe — verificar se está completo e responsivo

---

## Regras

1. Não remover funcionalidade existente
2. Toda ação deve ter feedback visual (success/error)
3. Botões destrutivos precisam de confirmação
4. Usar `run_cli()` de `dash_utils.py` para chamar operações
5. Não colocar SQL direto em arquivos de página — usar módulos

---

## Padrão de Implementação

```python
# Exemplo: botão de ação com feedback
col_a, col_b = st.columns([3, 1])
with col_b:
    if st.button("▶ Gerar card", key=f"card_{article_id}"):
        with st.spinner("Gerando..."):
            r = run_cli("make-card", "--scope", scope, "--limit", "1")
        if r["ok"]:
            st.success("✅ Card gerado!")
            st.rerun()
        else:
            st.error(f"❌ {r.get('error', 'Erro')}")
```

---

## Validação

```bash
# Testar dashboard localmente
streamlit run dashboard.py

# Verificar cada página manualmente:
# - Edições: criar dispatch dry-run, ver status
# - Operação: coletar, ver log
# - Lotes IA: gerar lote, importar JSON
# - Fontes: ver status de fontes
```

---

## Critérios de Aceite

- [ ] Editor consegue coletar feeds pelo dashboard
- [ ] Editor consegue gerar lote IA pelo dashboard
- [ ] Editor consegue importar resultado IA pelo dashboard
- [ ] Editor consegue aprovar/rejeitar artigo pelo dashboard
- [ ] Editor consegue ver status de cards pelo dashboard
- [ ] Editor consegue marcar como publicado pelo dashboard
- [ ] Todas as ações têm feedback visual
