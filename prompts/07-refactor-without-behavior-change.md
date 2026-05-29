# Prompt 07 — Refactor Agent: Sem Mudança de Comportamento

Use este prompt quando for solicitado a refatorar código **sem alterar comportamento**.

---

## Definição de "Sem Mudança de Comportamento"

Refatoração pura significa:
- Os mesmos inputs produzem os mesmos outputs
- As mesmas queries SQL retornam os mesmos dados
- Os mesmos endpoints da API retornam as mesmas respostas
- O mesmo CLI retorna o mesmo JSON
- Nenhum estado no banco é alterado de forma diferente
- Nenhuma dependência nova é instalada (sem adicionar ao requirements.txt)

**Se qualquer dessas condições puder ser violada, NÃO é refatoração pura.**

---

## Protocolo Obrigatório Antes de Refatorar

### 1. Leia o que existe

```bash
# Entenda o módulo que vai refatorar
cat src/news_radar/<modulo>.py

# Entenda quem usa o módulo
grep -rn "from .modulo import\|from news_radar.modulo import\|import modulo" src/ pages/ dashboard.py api_server.py
```

### 2. Identifique a interface pública

Liste **todas** as funções/classes exportadas pelo módulo.
Para cada uma, documente:
- Assinatura exata (parâmetros, tipos, defaults)
- O que retorna (tipo e estrutura)
- Efeitos colaterais (banco, arquivos, Telegram)

### 3. Escreva os testes de contrato ANTES de refatorar

Para cada função pública, crie um teste que:
- Chama a função com inputs representativos
- Salva o output atual como baseline
- Verifica que o output não muda após a refatoração

```python
# Exemplo: tests/test_refactor_baseline.py
def test_automatic_scores_contract():
    article = {
        "title": "Prefeitura de Teresina lança edital de licitação",
        "summary": "A Prefeitura de Teresina anunciou processo licitatório.",
        "source_scope": "teresina",
        "source_trust": 0.7,
        "published_at": None,
    }
    scores = automatic_scores(article)
    # Documente os valores baseline antes de refatorar:
    assert isinstance(scores["auto_score_brasil"], float)
    assert isinstance(scores["auto_score_teresina"], float)
    assert 0 <= scores["auto_score_brasil"] <= 100
    assert scores["auto_score_teresina"] > scores["auto_score_brasil"]
```

### 4. Confirme que testes passam ANTES de começar

```bash
python -m pytest tests/ -v
```

Se algum teste falhar antes de você começar, PARE. Não refatore sobre testes quebrados.

---

## Durante a Refatoração

### O que é PERMITIDO

- Renomear variáveis locais (dentro de uma função, sem afetar interface externa)
- Extrair funções privadas (prefixo `_`) que não são chamadas externamente
- Remover código morto óbvio (comentado há muito tempo, jamais chamado)
- Simplificar lógica com mesmo resultado (ex: `if x == True` → `if x`)
- Reorganizar ordem de funções no arquivo
- Melhorar mensagens de erro internas
- Adicionar type hints onde não existem
- Separar módulo grande em submódulos (APENAS se as importações externas continuam funcionando via `__init__.py`)

### O que é PROIBIDO

- Alterar assinatura de função pública (sem aprovação explícita)
- Alterar o que uma função retorna (tipo, keys, formato)
- Alterar SQL de queries existentes (mesmo resultado diferente pode quebrar indexes)
- Alterar regras de negócio como score formula, dedup logic, batch sizing
- Mover arquivos sem atualizar todas as importações
- Remover campos de JSONB retornado
- Alterar formato de datas, IDs ou hashes
- Substituir libraries (ex: psycopg2 → asyncpg) sem aprovação

### Regras específicas por módulo

| Módulo | O que preservar |
|--------|----------------|
| `ranker.py` | Fórmula exata de scores, lista de termos, pesos |
| `collector.py` | Lógica de upsert, dedup por canonical_url → title_signature |
| `ai_batches.py` | Estrutura de compact_article(), formato de batch_id |
| `card_renderer.py` | Placeholders `{{variavel}}`, viewport 600×400, locator #card |
| `dispatch.py` | Estados de status, fluxo approve → card → publish |
| `cli.py` | Todos os subcomandos e seus argumentos |
| `api_server.py` | Todos os endpoints, métodos HTTP, status codes |
| `db.py` | Schema SQL, migrate logic, connect() contextmanager |

---

## Verificação Pós-Refatoração

### 1. Testes de baseline devem continuar passando

```bash
python -m pytest tests/ -v
```

### 2. Smoke test manual dos fluxos críticos

```bash
# Fluxo 1: Coleta
python -m news_radar.cli collect --limit-per-feed 1

# Fluxo 2: Ranking
python -m news_radar.cli rank

# Fluxo 3: Stats
python -m news_radar.cli stats

# Fluxo 4: API health
curl http://localhost:8888/health
```

### 3. Verifique que importações externas ainda funcionam

```bash
python -c "from news_radar.ranker import automatic_scores, combine_with_ai; print('OK')"
python -c "from news_radar.collector import collect_feeds; print('OK')"
python -c "from news_radar.ai_batches import make_ai_batches, import_ai_result; print('OK')"
python -c "from news_radar.card_renderer import render_cards; print('OK')"
python -c "from news_radar.dispatch import create_dispatch, approve_article; print('OK')"
```

### 4. Dashboard ainda carrega sem erros

Inicie o Streamlit e navegue por todas as páginas, verificando que nenhum traceback aparece.

---

## Checklist de Entrega

Antes de considerar a refatoração concluída, verifique:

- [ ] Interface pública documentada ANTES e DEPOIS (assinaturas iguais)
- [ ] Testes de baseline passam antes e depois
- [ ] Nenhum arquivo movido sem atualizar importações
- [ ] `requirements.txt` não foi alterado
- [ ] Nenhum SQL alterado
- [ ] Nenhuma regra de negócio alterada
- [ ] Smoke tests do CLI funcionando
- [ ] Dashboard carrega sem erros
- [ ] `git diff` revisado linha a linha para confirmar que nada de comportamento mudou

---

## Quando Parar e Pedir Confirmação

Pare e peça aprovação ao usuário se:
- Perceber que a "refatoração" requer mudar uma assinatura de função
- Perceber que um SQL precisaria ser alterado para a refatoração fazer sentido
- Perceber que há comportamento ambíguo que você não sabe se deve preservar
- O escopo crescer além do módulo original

**Não tente resolver ambiguidades silenciosamente em uma refatoração.**

---

## Exemplos de Refatoração Segura

### ✅ Extrair função privada

```python
# ANTES
def automatic_scores(article):
    title = article.get("title") or ""
    summary = article.get("summary") or ""
    text = f"{title}. {summary}"
    public_count = sum(1 for term in PUBLIC_ORG_TERMS if term in text.lower())
    # ... etc

# DEPOIS
def _extract_text(article: dict) -> str:
    return f"{article.get('title') or ''}. {article.get('summary') or ''}"

def automatic_scores(article):
    text = _extract_text(article)
    public_count = count_terms(text, PUBLIC_ORG_TERMS)
    # ... etc (resultado idêntico)
```

### ✅ Simplificar condição

```python
# ANTES
if value is not None and value != "" and len(str(value)) > 0:

# DEPOIS
if value:
```

### ❌ PROIBIDO: Alterar formato de retorno

```python
# ANTES — retorna dict com "reasons" como lista de strings
return {"auto_score_brasil": 42.5, "reasons": ["órgão público: 2"]}

# DEPOIS — PROIBIDO: mudar para "score_reasons" ou tuple
return {"auto_score_brasil": 42.5, "score_reasons": [...]}  # ← quebra código que espera "reasons"
```

### ❌ PROIBIDO: Alterar regra de negócio

```python
# ANTES — penalidade por ausência de termos locais
if piaui_count == 0 and teresina_count == 0 and source_scope == "brasil":
    score_piaui *= 0.55

# DEPOIS — PROIBIDO: mudar o multiplicador
if piaui_count == 0 and teresina_count == 0 and source_scope == "brasil":
    score_piaui *= 0.60  # ← altera ranking de centenas de artigos
```
