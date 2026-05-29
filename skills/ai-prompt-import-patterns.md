# Skill — Padrões de IA Assistida (News Radar)

Referência para agentes implementando ou modificando o fluxo de IA.

---

## Regras Fundamentais

1. **IA não é fonte factual** — IDs retornados devem ser validados contra o banco
2. **Prompt sempre instrui usar apenas o lote fornecido**
3. **Resposta sempre JSON** — sem markdown, sem texto antes/depois
4. **Schema validado antes de importar**
5. **Salvar prompt e resposta bruta** para auditoria
6. **IA não decide publicação** — editor tem sempre a palavra final

---

## Estrutura do Prompt

```
[Regras obrigatórias]
  - Use apenas o conteúdo do lote
  - Não busque fontes externas
  - Devolva apenas JSON válido
  - Se campo não puder ser inferido, use valor neutro

[Objetivo]
  - Contexto editorial do sistema

[Campos a retornar por artigo]
  - id (mesmo recebido — não altere)
  - campos editoriais
  - scores numéricos 0-10

[Critérios gerais de scoring]
  - regras por dimensão

[Contexto do escopo]
  ESCOPO: BRASIL | PIAUÍ | TERESINA
  (siglas, órgãos, nomes relevantes)

[Lote de notícias]
  [JSON compacto dos artigos]
```

---

## Compactação do Artigo para o Prompt

```python
# ai_batches.py::compact_article()
compact = {
    "id": article["id"],           # OBRIGATÓRIO — não alterar
    "titulo": article["title"],
    "fonte": article["source"],
    "data_publicacao": str(published_at)[:16],
    "resumo": summary[:900],       # truncado
    "url": canonical_url,
}
```

Nunca incluir `raw_json` completo no prompt — muito volumoso.

---

## Campos Esperados na Resposta

```json
{
    "id": "abc123def456",
    "editoria": "Governos e politica",
    "categoria": "Licitação municipal",
    "localidade": "Teresina",
    "entidades": ["Prefeitura de Teresina", "STRANS"],
    "interesse_publico": 8,
    "impacto_social": 7,
    "gravidade": 6,
    "risco_investigativo": 9,
    "dinheiro_publico": 8,
    "relevancia_politica": 5,
    "polemica": 4,
    "urgencia": 7,
    "relevancia_local": 9,
    "confiabilidade": 8,
    "prioridade": "alta",
    "resumo_curto": "Prefeitura licita R$12mi em ônibus com indício de sobrepreço.",
    "titulo_sugerido": "Teresina paga 40% acima do mercado em licitação de ônibus",
    "subtitulo_sugerido": "MP investiga contrato da STRANS que pode ter superfaturamento",
    "pontos_chave": ["Contrato de R$12 milhões", "Preço 40% acima do mercado", "MP abriu inquérito"],
    "tags": ["licitação", "STRANS", "Teresina", "superfaturamento"],
    "justificativa_score": "Alto risco investigativo por dinheiro público e indício de irregularidade"
}
```

---

## Validação Antes de Importar

```python
# Validação em 2_Lotes_IA.py::_validate()
def _validate(texto: str, batch: dict) -> dict:
    # 1. JSON parse
    try: data = json.loads(content)
    except: return {"ok": False, "error": "JSON inválido"}

    # 2. Verificar se é lista
    if not isinstance(data, list): return {"ok": False, "error": "Deve ser lista"}

    # 3. Contar IDs que batem com os do lote
    result_ids = {str(item.get("id")) for item in data if isinstance(item, dict)}
    expected_ids = {ids do payload original}
    match_pct = len(result_ids & expected_ids) / len(expected_ids) * 100

    # 4. Threshold
    if match_pct < 40: return {"ok": False, "error": "Menos de 40% dos IDs reconhecidos"}
```

---

## Thresholds de Match

| % de IDs reconhecidos | Status | Ação |
|-----------------------|--------|------|
| ≥ 80% | ✅ Sucesso | Importar |
| 40–79% | ⚠️ Aviso | Importar com alerta |
| < 40% | ❌ Erro | Bloquear importação |
| IDs completamente errados | ❌ Lote errado | Bloquear importação |

---

## Exibição de Erros

```python
# Sempre exibir antes de importar
if not validation["ok"]:
    st.error(f"❌ {validation['error']}")
    # botão de importar desabilitado: disabled=not can_import
```

---

## Salvamento de Prompt e Resposta

```python
# Prompts: data/ai_batches/{batch_id}.prompt.txt
# Payloads: data/ai_batches/{batch_id}.json
# Resultados: data/ai_results/{batch_id}.result.json
```

Nunca sobrescrever resultado importado. Se reimportar, usar novo nome ou versão.

---

## Lote Não Deve Usar IDs de Outro Lote

```python
# Ao importar, verificar se ID existe no banco
cur.execute("SELECT id FROM articles WHERE id = %s", (item["id"],))
if not row:
    ignored += 1
    logs.append({"status": "não encontrado", "motivo": "ID não existe no banco"})
    continue
```

---

## Compatibilidade com Campos Legados

```python
# ranker.py::ai_score_from_payload()
# Suporta tanto campos modernos quanto legados
modern_fields = ["interesse_publico", "impacto_social", "urgencia", "relevancia_local", "dinheiro_publico"]
legacy_fields = ["impacto_publico", "gravidade", "relevancia_politica", "risco_investigativo", "dinheiro_publico"]
fields = modern_fields if any(f in payload for f in modern_fields) else legacy_fields
```

---

## O Que Não Fazer

- Não aceitar campos inventados pela IA sem tratamento
- Não importar IDs que não existem no banco
- Não substituir `ai_json` de artigos de outros lotes
- Não chamar API de IA diretamente sem consentimento explícito
- Não confiar no `titulo_sugerido` como título final — é sugestão
