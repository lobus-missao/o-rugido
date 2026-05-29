# Spec 07 — IA Assistida

**Status:** Funcional — documentar e manter
**Fase:** 4 (melhorias) / Atual funciona

---

## Princípio Fundamental

O sistema NÃO chama API de IA diretamente. O fluxo é inteiramente manual:

```
Sistema gera prompt → Usuário copia → Usuário processa em IA externa → Usuário cola JSON → Sistema valida → Sistema importa
```

Isso garante:
- Sem custo automático de API
- Editor tem visibilidade total do que é enviado
- Rollback possível
- Funciona com qualquer IA (ChatGPT, Claude, Gemini, Ollama local)

---

## Fluxo Completo

### 1. Criação do Lote

```python
# ai_batches.py::make_ai_batches()
make_ai_batches(
    scope="brasil",    # brasil | piaui | teresina
    top=200,           # artigos mais bem ranqueados
    batch_size=30,     # artigos por lote
    days_back=3,       # apenas artigos recentes
)
```

**O que acontece:**
1. Busca top artigos por `final_score_{scope}` (artigos sem ai_score priorizados)
2. Compacta cada artigo: {id, titulo, fonte, data, resumo, url}
3. Particiona em lotes respeitando limite de tokens (~96k tokens/lote)
4. Gera `{batch_id}.prompt.txt` e `{batch_id}.json` em `data/ai_batches/`
5. Registra lote em `ai_batches` com status `pending`

### 2. Estrutura do Prompt

```
[Template base de prompts/ai_batch_prompt_template.txt]
+
[Contexto do escopo: ESCOPO_CONTEXT[scope]]
+
LOTE DE NOTICIAS:
[JSON compacto dos artigos]
```

O template instrui a IA a retornar apenas JSON válido, usar apenas dados do lote, e preencher campos específicos.

### 3. Processo Manual pelo Editor

```
Dashboard > Lotes IA > Lotes pendentes
↓
Ver prompt → Copiar para clipboard
↓
Abrir ChatGPT ou Claude
↓
Colar prompt → Executar
↓
Copiar resposta JSON
↓
Colar na textarea da dashboard
↓
Validar (automático)
↓
Importar se válido (≥40% IDs reconhecidos)
```

### 4. Validação Antes de Importar

```python
# pages/2_Lotes_IA.py::_validate()
def _validate(texto: str, batch: dict) -> dict:
    # 1. Verificar se é JSON válido
    # 2. Verificar se é lista
    # 3. Contar IDs que batem com os esperados do lote
    # 4. Retornar: ok, matched, total_expected, match_pct, wrong_batch
```

Thresholds:
- `match_pct >= 80%` → sucesso verde
- `match_pct >= 40%` → aviso amarelo, importação permitida
- `match_pct < 40%` → erro, importação bloqueada
- `wrong_batch == True` → erro, lote errado

### 5. Importação

```python
# ai_batches.py::import_ai_result_detailed()
for item in data:
    # 1. Verificar item tem 'id'
    # 2. Buscar artigo no banco por id
    # 3. Calcular ai_score a partir dos campos numéricos
    # 4. Calcular final_score combinando auto + ai
    # 5. Atualizar: ai_score, ai_json, category, locality, priority, entities_json, final_scores
    # 6. Logar resultado por artigo
```

### 6. Campos Retornados pela IA

```json
{
    "id": "abc123",
    "editoria": "Governos e politica",
    "categoria": "Licitação",
    "localidade": "Teresina",
    "entidades": ["Prefeitura de Teresina", "STRANS"],
    "interesse_publico": 8,
    "impacto_social": 7,
    "gravidade": 6,
    "risco_investigativo": 9,
    "dinheiro_publico": 8,
    "relevancia_politica": 5,
    "polemica": 6,
    "urgencia": 7,
    "relevancia_local": 9,
    "confiabilidade": 8,
    "prioridade": "alta",
    "resumo_curto": "Prefeitura licitou ônibus com sobrepreço de 40%.",
    "titulo_sugerido": "Teresina paga 40% acima do mercado em ônibus",
    "subtitulo_sugerido": "Licitação de R$12mi tem indícios de superfaturamento",
    "pontos_chave": ["Contrato de R$12 milhões", "40% acima do mercado", "MP investiga"],
    "tags": ["licitação", "ônibus", "Teresina", "superfaturamento"],
    "justificativa_score": "Alto risco investigativo e dinheiro público elevado"
}
```

---

## Contextos por Escopo

O prompt inclui contexto geográfico específico:

**Brasil:** foco em impacto nacional, STF, TCU, CGU, PF, Senado, Câmara
**Piauí:** ALEPI, TCE-PI, MPPI, TJPI, Governo Fonteles, secretarias estaduais
**Teresina:** Prefeitura, Câmara Municipal, FMS, SEMEC, STRANS, vereadores

---

## Compactação de Artigos

```python
# ai_batches.py::compact_article()
{
    "id": article["id"],           # ID original (obrigatório na resposta)
    "titulo": article["title"],
    "fonte": article["source"],
    "data_publicacao": str(published_at)[:16],
    "resumo": summary[:900],       # truncado para economizar tokens
    "url": canonical_url,
}
```

---

## Estimativa de Tokens

```python
# ai_batches.py::estimate_text_metrics()
tokens = max(1, math.ceil(len(text) / 4))
```

Limites por lote:
- `DEFAULT_TARGET_BATCH_TOKENS = 96_000`
- `DEFAULT_MAX_BATCH_TOKENS = 128_000`
- `DEFAULT_BATCH_ITEMS = 100`

---

## Log de Importação

Retornado por `import_ai_result_detailed()`:

```python
logs = [
    {"status": "atualizado", "id": "...", "titulo": "...", "editoria": "...",
     "prioridade": "alta", "ai_score": 8.5, "resumo": "...", "justificativa": "..."},
    {"status": "não encontrado", "id": "...", "motivo": "ID não existe no banco"},
    {"status": "erro", "id": "...", "motivo": "campo inválido: ..."},
]
```

---

## Histórico de Importação

- Lote marcado como `completed` após importação bem-sucedida
- `imported_count` e `ignored_count` registrados no lote
- `result_path` aponta para arquivo JSON salvo em `data/ai_results/`
- Prompt salvo em `data/ai_batches/{batch_id}.prompt.txt`

---

## Rollback / Rejeição

Atualmente: não há rollback automático de importação.

Futuro (Fase 4):
- Campo `ai_import_version` em articles
- Possibilidade de reverter para ai_score anterior
- Lote pode ser reimportado: nova importação sobrescreve ai_json e scores

---

## Critérios de Aceite

- [ ] Prompt gerado contém contexto do escopo correto
- [ ] IDs no prompt correspondem aos IDs no banco
- [ ] JSON com IDs errados (< 40% match) bloqueia importação
- [ ] JSON inválido exibe erro antes de importar
- [ ] Log detalhado mostra status por artigo
- [ ] Lote marcado como `completed` após importação
- [ ] `ai_json` salvo no banco com todos os campos retornados
- [ ] `final_score_*` recalculado após importação
- [ ] Importação sem erros não altera artigos de outros lotes
