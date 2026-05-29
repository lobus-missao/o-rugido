# Prompt 04 — IA Assistida (Fase 4)

---

## Contexto

O fluxo de IA já existe e funciona: gerar lote → copiar prompt → colar JSON → importar. O objetivo desta fase é adicionar melhorias de qualidade de vida sem quebrar o que funciona.

---

## Spec de Referência

Leia: `specs/07-ai-assisted-processing.md`

---

## Melhorias a Implementar

### 1. Botão de Cópia do Prompt

Atualmente o usuário copia manualmente da textarea. Adicionar botão:

```python
# Usar st.code() que tem botão de cópia nativo
st.code(prompt_text, language=None)
# ou
if st.button("📋 Copiar prompt"):
    st.write('<script>navigator.clipboard.writeText(`' + prompt_text + '`)</script>',
             unsafe_allow_html=True)
```

### 2. Exibir Métricas do Lote

Antes de gerar o lote:
```python
metrics = estimate_batch_metrics(scope, compact_articles[:batch_size])
st.caption(f"~{metrics['estimated_tokens']:,} tokens estimados · {metrics['estimated_words']:,} palavras")
```

### 3. Reimportação de Resultado

Permitir reimportar resultado de lote já concluído:
```python
# Botão "Reimportar" em lotes completados
if st.button("🔄 Reimportar"):
    result_path = AI_RESULTS_DIR / f"{batch_id}.result.json"
    if result_path.exists():
        imported = import_ai_result_detailed(result_path, batch_id=batch_id)
        st.success(f"Reimportado: {imported['updated']} atualizados")
```

### 4. Validação em Tempo Real

Já existe. Verificar se threshold de 40% está bem explicado para o usuário.

---

## Regras

1. Não alterar `import_ai_result_detailed()` — é estável
2. Não alterar `make_ai_batches()` — é estável
3. Melhorias são apenas na UI (pages/2_Lotes_IA.py)
4. Manter compatibilidade com prompts já gerados
5. Nunca chamar API de IA diretamente sem aprovação

---

## Validação

```bash
# Gerar lote
python -m news_radar.cli make-ai-batches --scope brasil --top 30 --batch-size 10

# Verificar arquivo gerado
ls data/ai_batches/

# Importar resultado de teste
python -m news_radar.cli import-ai --file data/ai_results/exemplo.result.json

# Verificar que artigos foram atualizados
python -m news_radar.cli stats
```

---

## Critérios de Aceite

- [ ] Prompt pode ser copiado com um clique
- [ ] Métricas do lote exibidas antes de gerar
- [ ] Validação em tempo real ao colar JSON
- [ ] Log detalhado por artigo após importação
- [ ] Lote completado pode ser reimportado
- [ ] Artigos sem match de ID reportados claramente
