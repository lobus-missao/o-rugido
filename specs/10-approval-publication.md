# Spec 10 — Aprovação e Publicação

**Status:** Funcional via Telegram / Em evolução para dashboard
**Fase:** 8

---

## Estado Atual

Aprovação funciona via Telegram (botões inline) processados pelo `telegram_poller.py` ou endpoint `/api/telegram/callback`. Estados gerenciados em `dispatches`. Dashboard pode marcar como publicado.

---

## Estados do Dispatch

```
pending_article    → artigo enviado ao Telegram, aguardando aprovação
article_approved   → artigo aprovado, card sendo gerado
article_rejected   → artigo rejeitado pelo editor
pending_card       → card enviado ao Telegram, aguardando aprovação
card_rejected      → card rejeitado, pode ser regerado
ready_to_publish   → card aprovado, pronto para postagem
published          → marcado como publicado manualmente
```

## Estados do Editorial Status (em `articles`)

```
discovered         → capturado, sem análise
needs_ai           → marcado para processamento por IA
ai_done            → IA processou, aguarda seleção editorial
selected           → selecionado para edição
sent_to_telegram   → enviado para aprovação via Telegram
approved           → artigo aprovado  ⚠️ ver nota abaixo
rejected           → artigo rejeitado
ready_to_publish   → card aprovado    ← escrito por approve_card()
published          → publicado        ← escrito por mark_published()
archived           → arquivado
card_rejected      → card rejeitado   ← escrito por reject_card()
```

> **⚠️ Nota importante sobre `editorial_status = 'approved'`:**
> Este estado **não é escrito pelo fluxo de dispatch atual**. `dispatch.approve_article()` atualiza
> `dispatches.status = 'article_approved'`, mas não atualiza `articles.editorial_status`.
> O estado `'approved'` existe no enum por compatibilidade histórica (migration legacy) e para
> uso manual futuro (ex: editor marca diretamente na dashboard).
> 
> Na Fase 8, será adicionado `UPDATE articles SET editorial_status='approved'` dentro de
> `approve_article()` para corrigir esta lacuna.
> 
> **Não filtre artigos por `editorial_status = 'approved'` esperando encontrar os aprovados
> pelo dispatch — use `dispatches.status = 'article_approved'` para isso.**

---

## Aprovação de Artigo

### Via Telegram (atual)

Botões inline: `✅ Aprovar` / `❌ Rejeitar`

```python
# dispatch.py::approve_article(dispatch_id, user, generate_card=True)
# 1. Verifica status == pending_article
# 2. Atualiza: status=article_approved, article_reviewed_by=user, article_reviewed_at=now
# 3. Edita mensagem Telegram: mostra "✅ APROVADO por {user}"
# 4. Chama generate_card_for_dispatch() se generate_card=True
```

### Via Dashboard (futura melhoria)

```python
# Botão "✅ Aprovar" na página de Edições
dispatch.approve_article(dispatch_id, user=st.session_state.get("user", "Editor"))
```

---

## Rejeição de Artigo

```python
# dispatch.py::reject_article(dispatch_id, user)
# 1. Verifica status == pending_article
# 2. Atualiza: status=article_rejected, article_reviewed_by=user, article_reviewed_at=now
# 3. Edita mensagem Telegram: "❌ REJEITADO por {user}"
```

---

## Aprovação de Card

```python
# dispatch.py::approve_card(dispatch_id, user)
# 1. Verifica status in (pending_card, card_approved, ready_to_publish)
# 2. Atualiza: status=ready_to_publish, card_reviewed_by, card_reviewed_at, ready_at
# 3. Edita caption Telegram
# 4. Atualiza articles: editorial_status=ready_to_publish, card_status=approved
```

---

## Rejeição de Card

```python
# dispatch.py::reject_card(dispatch_id, user)
# Atualiza: status=card_rejected, card_reviewed_by, card_reviewed_at
# Atualiza articles: editorial_status=card_rejected, card_status=rejected
```

Após rejeição de card: editor pode regenerar via:
- Botão 🔄 no Telegram
- Botão "Regerar card" na dashboard

---

## Comentário do Revisor (Futuro)

Campo futuro no dispatch:
```sql
review_notes TEXT
```

Permite editor deixar observação ao rejeitar.

---

## Usuário / Reviewer

- Via Telegram: `user_data.get("username") or user_data.get("first_name") or "Telegram"`
- Via dashboard: `st.session_state.get("user", "Editor")`
- Via API n8n: campo `reviewer` no payload

---

## Publicação Manual

```python
# dispatch.py::mark_published(dispatch_id)
# Atualiza: dispatch.status=published
# Atualiza: articles.editorial_status=published
```

Interface: botão "Marcar como publicado" na página de Edições.

---

## Integração com Telegram (Atual)

**Estratégia A (MVP local):**
- `telegram_poller.py` faz polling `getUpdates`
- Callbacks processados por `dispatch.handle_callback_action(action, payload, user)`
- Não usar simultâneo com webhook

**Estratégia B (produção):**
- Webhook Telegram → n8n ou endpoint direto → `POST /api/telegram/callback`
- Configurar via: `python -m news_radar.cli telegram-webhook --action set --url ...`

---

## Integração Opcional com n8n

n8n pode chamar:
- `POST /api/dispatch/run` → criar dispatch e enviar ao Telegram
- `POST /api/review/news` → aprovar/rejeitar artigo
- `POST /api/review/card` → aprovar/rejeitar card

Mas n8n NÃO deve decidir qual ação tomar — apenas encaminhar comandos do editor.

---

## Auditoria de Aprovação (Futuro)

Tabela `editorial_actions`:
```sql
INSERT INTO editorial_actions (article_id, dispatch_id, action, actor, from_status, to_status, notes)
VALUES (...);
```

Atualizar: `dispatch.approve_article()`, `reject_article()`, `approve_card()`, `reject_card()`.

---

## Critérios de Aceite

- [ ] Aprovação de artigo cria registro de quem aprovou e quando
- [ ] Rejeição bloqueia artigo de nova seleção no mesmo dia
- [ ] Aprovação de card dispara geração se card não existe
- [ ] Status no Telegram reflete estado atual (mensagem editada)
- [ ] Dashboard mostra status correto para cada dispatch
- [ ] `mark_published` atualiza ambas tabelas (dispatches + articles)
- [ ] Dupla aprovação não processa novamente (idempotente)
