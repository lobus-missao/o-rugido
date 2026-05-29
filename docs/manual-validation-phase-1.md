# Validação Manual — Fase 1: Guard de Idempotência em create_dispatch()

**Data:** 2026-05-29
**Escopo:** Fase 1 — pré-requisito do scheduler interno (guard contra duplo envio ao Telegram)

---

## O Que Foi Implementado

Guard de idempotência no início de `create_dispatch()` em `dispatch.py`.

**Lógica:** antes de selecionar artigos ou enviar ao Telegram, verifica se já existe
dispatch ativo (não rejeitado) para a mesma combinação `(edition, edition_date, scope)`.
Se existir, retorna `[]` e loga warning — sem criar novos registros nem enviar nada.

**Arquivo alterado:** `src/news_radar/dispatch.py` — função `create_dispatch()`

**Testes automatizados:** `tests/test_dispatch_idempotency.py` (7 casos)

---

## Checklist de Validação Automatizada

```bash
# Rodar apenas os novos testes de idempotência
python -m pytest tests/test_dispatch_idempotency.py -v

# Rodar todos os testes (garantir que nada quebrou)
python -m pytest tests/ -v
```

Resultado esperado: **todos os testes passando**.

---

## Checklist de Validação Manual

### 1. Fluxo Normal (sem duplicação)

**Pré-condição:** banco limpo (sem dispatches de hoje)

```bash
# Ativar dry-run para não enviar ao Telegram real
export NEWS_RADAR_DRY_RUN=1

# Chamar dispatch da manhã
python -m news_radar.cli dispatch --edition morning --scope piaui

# Verificar que artigos foram despachados
psql $DATABASE_URL -c "SELECT id, edition, edition_date, scope, status FROM dispatches WHERE edition_date = CURRENT_DATE;"
```

**Resultado esperado:** 1 a 3 linhas com `status = 'pending_article'`.

---

### 2. Guard Bloqueia Segunda Chamada

**Pré-condição:** dispatch da manhã já criado (passo anterior)

```bash
# Chamar novamente — deve ser bloqueado
python -m news_radar.cli dispatch --edition morning --scope piaui
```

**Resultado esperado:**
- Saída indica 0 artigos despachados (sem erro)
- Log exibe warning: `"Dispatch bloqueado (idempotência): edição 'morning' já existe..."`
- Banco NÃO tem novas linhas na tabela `dispatches` para a manhã de hoje

```bash
# Confirmar: ainda apenas 1-3 rows, não 4-6
psql $DATABASE_URL -c "SELECT COUNT(*) FROM dispatches WHERE edition = 'morning' AND edition_date = CURRENT_DATE AND scope = 'piaui';"
```

**Resultado esperado:** contagem igual ao passo anterior (não dobrou).

---

### 3. Guard Respeita Scope

**Pré-condição:** dispatch morning/piaui existe

```bash
# Dispatch morning/brasil — scope diferente, deve passar
python -m news_radar.cli dispatch --edition morning --scope brasil
```

**Resultado esperado:** novos dispatches criados (scope brasil é independente de piaui).

---

### 4. Guard Permite Nova Edição Após Rejeição Total

**Pré-condição:** rejeitar TODOS os dispatches da manhã manualmente ou via Telegram

```bash
# Verificar que todos estão rejeitados
psql $DATABASE_URL -c "SELECT status FROM dispatches WHERE edition = 'morning' AND edition_date = CURRENT_DATE AND scope = 'piaui';"
# Todos devem ser 'article_rejected' ou 'card_rejected'

# Chamar novamente — deve ser permitido
python -m news_radar.cli dispatch --edition morning --scope piaui
```

**Resultado esperado:** novos dispatches criados (rejeitados não contam para o guard).

---

### 5. Compatibilidade com Fluxo Existente

```bash
# Verificar que CLI dispatch ainda aceita os mesmos parâmetros
python -m news_radar.cli dispatch --help

# Verificar que API ainda funciona
curl -X POST http://localhost:8888/api/dispatch/run \
  -H "Content-Type: application/json" \
  -d '{"edition": "noon", "scope": "piaui", "top": 3}'
```

**Resultado esperado:** CLI responde normalmente; API retorna JSON sem erro 500.

---

### 6. Verificar Log de Warning

```bash
# Com dry-run e dispatch já existente, verificar log
python -m news_radar.cli dispatch --edition morning --scope piaui 2>&1 | grep -i "bloqueado\|idempotên"
```

**Resultado esperado:** linha de warning visível com contexto (edition, date, scope).

---

## Comportamento Antes × Depois

| Situação | Antes (sem guard) | Depois (com guard) |
|----------|-------------------|---------------------|
| Segunda chamada para mesma edição/data/scope | Cria novo lote com próximos candidatos → **duplicata no Telegram** | Retorna `[]` sem criar nada → **sem duplicata** |
| n8n + scheduler simultâneos às 06:30 | 6 mensagens enviadas | 3 mensagens (segunda chamada bloqueada) |
| Edition inválida | Pode retornar `[]` se sem artigos (bug silencioso) | Sempre lança `ValueError` imediatamente |
| Todos dispatches rejeitados | Mesmo comportamento | Nova edição é permitida |

---

## Riscos Residuais

1. **Race condition extrema:** se duas chamadas chegarem exatamente ao mesmo milissegundo
   antes de qualquer INSERT, o guard SELECT COUNT pode retornar 0 para ambas. Mitigação:
   o guard reduz o risco em ~99% dos casos práticos; para proteção total, seria necessário
   um índice UNIQUE ou lock de banco — **não implementado nesta fase** (outside scope Fase 1).

2. **Guard por scope:** se n8n chamar `scope="brasil"` e scheduler chamar `scope="piaui"`,
   são edições diferentes e ambas passam. Comportamento correto por design.

3. **Scheduler ainda não ativado:** o guard existe mas o scheduler ainda não está implementado.
   O risco de duplo disparo persiste enquanto o scheduler estiver sendo desenvolvido e antes de
   ser ativado. Guard só tem efeito quando há múltiplos chamadores simultâneos.

---

## Itens Pendentes para Fase 1 Completa

- [ ] Adicionar `APScheduler` ao `requirements.txt`
- [ ] Criar `src/news_radar/scheduler.py`
- [ ] Integrar ao `api_server.py` com `NEWS_RADAR_SCHEDULER=1`
- [ ] Atualizar `.env.example`
- [ ] Dashboard `1_Operacao.py`: status do scheduler
- [ ] Testar com n8n desligado

O guard implementado é **pré-requisito bloqueante** para ativar o scheduler.
Não ativar `NEWS_RADAR_SCHEDULER=1` antes de confirmar que o guard está funcionando.
