# Revisão da Base SDD — News Radar RSS

**Data:** 2026-05-29
**Revisor:** Review Agent
**Escopo:** Fase 0 — Diagnóstico e SDD

---

## Veredicto Global

**APROVADO COM RESSALVAS**

A base SDD está sólida, baseada no projeto real, e bem alinhada com os princípios declarados em AGENTS.md. Nenhuma restrição absoluta foi violada. Os problemas encontrados são localizados e corrigíveis sem reescrever nada.

**O que está muito bem:**
- Specs refletem o código que existe de facto — não arquitetura inventada
- Separação n8n / Python muito bem documentada
- Fluxo de IA assistida corretamente descrito e delimitado
- Modelo de dados fiel ao schema real do banco
- Skills e prompts são concretos e acionáveis

**O que precisa de ajuste antes da Fase 1:**
- 1 claim de segurança falso sobre duplo disparo (risco real)
- 1 contradição sobre `raw_json` (imutável vs atualizado)
- 1 inconsistência de fases entre spec/03 e tasks.md
- 2 placeholders no template novo não implementados no renderer
- 1 estado editorial listado que nunca é definido pelo código real

---

## Problemas Encontrados

### [CRÍTICO-1] — Claim falso de proteção contra duplo disparo

**Onde:** `specs/12-n8n-decoupling.md`, seção "Prevenção de duplo disparo"

**O que diz a spec:**
> "`create_dispatch()` verifica se já existe dispatch para a edição/data antes de criar"

**O que o código faz na realidade** (`dispatch.py::create_dispatch()`):
```python
# Só exclui artigos já despachados hoje, mas NÃO verifica se uma edição completa já existe
cur.execute("SELECT article_id FROM dispatches WHERE edition_date = %s", (today,))
already = {row["article_id"] for row in cur.fetchall()}
```

Se n8n e o scheduler Python ambos dispararem às 06:30, `create_dispatch(edition="morning")` seria chamado duas vezes. A segunda chamada encontraria os artigos originais já excluídos de `already`, mas selecionaria os próximos 3 candidatos e criaria um **segundo lote de dispatches para a mesma edição**. O resultado: 6 mensagens enviadas ao Telegram para a edição da manhã.

**Risco:** Alto. Pode ocorrer durante a transição quando n8n e scheduler interno coexistirem.

**Correção necessária na spec:** Remover o claim falso e documentar o risco real. Na implementação da Fase 1, adicionar guard em `create_dispatch()`:

```python
# Adicionar ao início de create_dispatch()
cur.execute(
    "SELECT COUNT(*) AS cnt FROM dispatches WHERE edition = %s AND edition_date = %s",
    (edition, today)
)
if cur.fetchone()["cnt"] > 0:
    return []  # edição já criada hoje
```

---

### [CRÍTICO-2] — Contradição sobre imutabilidade de `raw_json`

**Onde:** `specs/02-data-model.md` (regra 2) vs `specs/03-ingestion-sources.md` (seção Idempotência)

**spec/02 diz:**
> `raw_json` é imutável — dado bruto preservado mesmo após normalização

**spec/03 diz:**
> `raw_json`: atualizado mesmo em UPDATE para manter dado mais recente

**O que o código faz** (`collector.py::upsert_article()`, linha 98):
```python
cur.execute("""
    UPDATE articles SET
        ...
        raw_json = %s,   # ← É atualizado a cada coleta
        ...
""", ...)
```

**O código atualiza `raw_json` em cada UPDATE.** Spec/02 está errada ao chamá-lo "imutável". Se um agente implementar guiado pela spec/02, pode adicionar proteção que quebra o comportamento atual.

**Risco:** Médio. Um engenheiro lendo spec/02 pode "proteger" `raw_json` de updates, quebrando o registro do dado mais recente do feed.

**Correção necessária em spec/02:** Trocar "imutável" por: "`raw_json` é sempre atualizado para refletir o dado mais recente do feed — não remover esta coluna nem limitar seu update."

---

### [MÉDIO-1] — Inconsistência de fases entre spec/03 e tasks.md

**Onde:** `specs/03-ingestion-sources.md` header vs `tasks.md`

**spec/03 diz:**
> `**Fase:** 3 (fontes gerenciáveis) / Funcional atual para RSS`

**tasks.md Fase 3 é:**
> Dashboard como Cockpit Editorial

**tasks.md Fase 2 é:**
> Fortalecimento do Banco — inclui criar tabela `sources`

A implementação de "fontes gerenciáveis" (tabela `sources`) está prevista na **Fase 2**, não na Fase 3. Mas spec/03 aponta para Fase 3.

Se um engenheiro implementar a Fase 3 (dashboard) antes da Fase 2 (banco), a página `8_Fontes_RSS.py` que lista fontes com status não terá dados — porque a tabela `sources` ainda não foi criada.

**Risco:** Médio. Pode causar confusão sobre dependências de implementação.

**Correção necessária em spec/03:** Alterar o header para:
> `**Fase:** 2 (tabela sources) → 3 (UI fontes no dashboard)`

**Adicionar em tasks.md Fase 3** (critérios de aceite): "Requer Fase 2 completa para fontes gerenciáveis. A lista de fontes pode usar fallback para feeds.yaml se tabela sources estiver vazia."

---

### [MÉDIO-2] — Novos placeholders do template `card-editorial-base.html` não implementados no renderer

**Onde:** `templates/card-editorial-base.html` vs `src/news_radar/card_renderer.py`

O novo template usa:
- `{{subtitulo_html}}` — não existe em `_render_html()`
- `{{categoria_tag}}` — não existe em `_render_html()`

O template atual `card.html` usa `{{conteudo_tag}}` mas o novo usa `{{categoria_tag}}`.

Se alguém usar o `card-editorial-base.html` com o renderer atual, esses placeholders aparecerão como texto literal no card.

**Risco:** Médio. Qualquer uso do novo template antes de atualizar o renderer produz cards com `{{subtitulo_html}}` visível.

**Correção necessária:**
1. Adicionar comentário no `card-editorial-base.html`: `<!-- REQUER: card_renderer.py atualizado com suporte a subtitulo_html e categoria_tag -->`
2. Ou alinhar os placeholders ao conjunto já suportado por `_render_html()`
3. Adicionar à spec/09 e tasks.md Fase 7: "antes de usar card-editorial-base.html, atualizar _render_html() com subtitulo_html e categoria_tag"

---

### [MÉDIO-3] — Estado `editorial_status = 'approved'` nunca definido pelo fluxo de dispatch

**Onde:** `specs/10-approval-publication.md` e `specs/02-data-model.md`

Ambas as specs listam `'approved'` como estado válido do `editorial_status`. Mas `dispatch.approve_article()` faz:

```python
update_dispatch(
    dispatch_id,
    status="article_approved",          # ← muda dispatches.status
    article_reviewed_by=user,
    article_reviewed_at=utc_now(),
)
# NÃO atualiza articles.editorial_status
```

O `editorial_status` só é atualizado em:
- `approve_card()` → `'ready_to_publish'`
- `reject_card()` → `'card_rejected'`
- `mark_published()` → `'published'`

O estado `'approved'` nunca é escrito pelo dispatch flow. Só pela migration inicial (via mapeamento de `card_status`).

**Risco:** Baixo-médio. Pode gerar confusão na Fase 3 quando o dashboard precisar filtrar por `editorial_status = 'approved'` e não encontrar artigos nesse estado.

**Correção recomendada:**
- Em spec/10 e spec/02: anotar que `'approved'` pode ser definido apenas manualmente ou pela migration histórica, não pelo fluxo dispatch atual.
- No código futuro (Fase 8): considerar adicionar `UPDATE articles SET editorial_status='approved'` dentro de `approve_article()`.

---

### [MENOR-1] — APScheduler em Flask multi-worker não abordado

**Onde:** `specs/12-n8n-decoupling.md`, seção "Etapa 1.2 — Inicialização Condicional"

A spec recomenda iniciar o scheduler dentro de `api_server.py`. O `BackgroundScheduler` do APScheduler se comporta incorretamente com múltiplos workers de processo (gunicorn, uwsgi) — cada worker inicia um scheduler independente, resultando em N coletas paralelas.

O docker-compose atual usa `python api_server.py` (Flask single-process), então não é um problema imediato. Mas a spec não avisa sobre essa limitação.

**Risco:** Baixo no setup atual. Torna-se risco alto se for para produção com gunicorn.

**Correção recomendada:** Adicionar aviso na spec/12:
> ⚠️ APScheduler com BackgroundScheduler é compatível apenas com execução single-process. Se usar gunicorn com múltiplos workers, usar APScheduler com job store persistente (Redis/DB) ou inicializar o scheduler em processo separado.

---

### [MENOR-2] — Viewport do Playwright (600px) vs largura do card (580px)

**Onde:** `specs/09-card-template-renderer.md`

A spec menciona `viewport={"width": 600, "height": 400}` mas o `#card` tem `width: 580px`. O screenshot captura o elemento `#card` via `page.locator("#card").screenshot()`, então o viewport não é o problema — o screenshot tem 580px independentemente. Mas a spec poderia ser mais precisa.

**Risco:** Nenhum. Apenas imprecisão documental.

---

### [MENOR-3] — Spec/07 menciona `ai_import_version` mas não está no modelo de dados

**Onde:** `specs/07-ai-assisted-processing.md` (Rollback), `specs/02-data-model.md`

Spec/07 menciona:
> Campo `ai_import_version` em articles

Mas spec/02 não lista este campo no modelo futuro de `articles`.

**Risco:** Baixo. Campo futuro não implementado. Mas cria inconsistência de referência cruzada.

**Correção recomendada:** Adicionar em spec/02 na seção de campos futuros de `articles`:
```sql
ai_import_version INTEGER DEFAULT 0,  -- contador de importações IA (para rollback)
ai_import_previous_json JSONB,        -- backup do ai_json anterior à última importação
```

---

## Validação por Dimensão

### Specs: específicas demais ou genéricas demais?

| Spec | Avaliação |
|------|-----------|
| spec/00 produto | ✅ Nível correto — visão sem detalhe de implementação |
| spec/01 arquitetura | ✅ Bem balanceado, fronteiras claras |
| spec/02 dados | ✅ Específico com schema real + tabelas futuras bem separadas |
| spec/03 ingestão | ⚠️ Fase incorreta (ver MÉDIO-1). Conteúdo bom |
| spec/04 normalização | ✅ Documenta o existente sem inventar |
| spec/05 dedup/clustering | ✅ Deduplicação específica (implementada), clustering honestamente marcado como hipótese |
| spec/06 ranking | ✅ Documenta fórmula real com precisão. Evolução bem separada |
| spec/07 IA assistida | ✅ Fluxo muito bem detalhado, limites claros |
| spec/08 dashboard | ⚠️ Alguns itens como "Marcar como needs_ai" e "Selecionar para edição" no Radar não têm função Python mapeada. Aspiracionais sem implementação definida |
| spec/09 cards | ✅ Bem específico, template real documentado |
| spec/10 aprovação | ⚠️ Estado 'approved' nunca escrito pelo dispatch (ver MÉDIO-3) |
| spec/11 auditoria | ✅ Correto: documenta o existente e propõe o futuro |
| spec/12 n8n | ⚠️ Claim falso sobre duplo disparo (ver CRÍTICO-1). Resto bom |
| spec/13 segurança | ✅ Prático e baseado no projeto real |

### Plano de Desacoplamento do n8n

**Incremental?** ✅ Sim. Ativação via variável de ambiente, n8n mantido durante transição.

**Seguro?** ⚠️ Parcialmente. O guard contra duplo disparo está incorreto na spec (CRÍTICO-1). Precisará ser implementado no código antes de ativar o scheduler.

**Reversível?** ✅ Sim. Desabilitar `NEWS_RADAR_SCHEDULER=0` reverte ao n8n.

### Dashboard como Centro de Controle

✅ A spec/08 está bem estruturada. Todas as operações críticas têm mapeamento para funções Python existentes. O princípio de "sem terminal, sem n8n" está claramente especificado.

**Gap não bloqueante:** A spec não descreve como o usuário aciona uma nova edição manual pela dashboard (ex: segunda edição "noite extra"). Fluxo de criação de dispatch ad-hoc não documentado.

### IA Assistida

✅ Muito bem delimitada. Princípio "sem chamada automática a API paga" é claro e repetido em múltiplos documentos (AGENTS.md, spec/07, skill). Thresholds de validação documentados. Histórico de importação preservado.

**Ponto de atenção:** Spec/07 diz que artigos sem ai_score são priorizados no lote, mas `top_articles()` em `repository.py` ordena apenas por `final_score_*` sem diferenciar por presença de `ai_score`. Existe `only_with_score=True` que filtra score > 0, mas não prioriza sem-IA. A função `make_ai_batches()` chama `top_articles()` diretamente — então artigos que já têm IA mas têm score alto ficam no lote, misturados com artigos sem IA. Não é um bug crítico, mas a afirmação da spec não reflete o código exato.

### Geração de Cards

✅ Especificação correta e completa para o que existe. Template bem documentado com todos os placeholders mapeados.

**Risco identificado:** `card-editorial-base.html` tem placeholders novos não suportados pelo renderer (MÉDIO-2). Precisa de nota de "não usar até renderer atualizado".

### Risco de Quebrar o Fluxo Atual

A Fase 0 não alterou nenhum arquivo de código. Risco zero para o funcionamento atual.

Para a Fase 1 (próxima), os riscos são:
1. **Duplo disparo** (CRÍTICO-1) — mitigável com guard no início de `create_dispatch()`
2. Nenhum outro risco de regressão identificado para Fase 1

---

## Ajustes Recomendados

### Antes de iniciar Fase 1 (obrigatórios)

**AJ-1:** Corrigir spec/12 — remover claim falso sobre idempotência do `create_dispatch()` e documentar guard necessário.

**AJ-2:** Corrigir spec/02 — trocar "raw_json é imutável" por linguagem que reflete a realidade (atualizado a cada coleta).

**AJ-3:** Corrigir spec/03 — header de fase de "3" para "2→3".

**AJ-4:** Adicionar nota em `templates/card-editorial-base.html` indicando que requer atualização do renderer antes de uso.

### Antes de iniciar Fase 3 (recomendados)

**AJ-5:** Adicionar em tasks.md Fase 3 a dependência explícita: "Requer Fase 2 para `8_Fontes_RSS.py` com dados reais."

**AJ-6:** Corrigir spec/10 — anotar que `editorial_status = 'approved'` não é escrito pelo dispatch flow atual. Propor correção no código na Fase 8.

**AJ-7:** Detalhar em spec/08 quais ações da página Radar (needs_ai, selected) têm função Python correspondente vs quais são aspiracionais.

### Antes de iniciar Fase 7 (cards)

**AJ-8:** Alinhar os placeholders de `card-editorial-base.html` com `_render_html()`, ou documentar explicitamente as adições necessárias ao renderer.

**AJ-9:** Adicionar `ai_import_version` em spec/02 (modelo de dados futuro de `articles`).

---

## Ordem Ideal de Implementação

A ordem das tarefas está bem estruturada no tasks.md, com uma correção:

```
Fase 0 ✅ Concluída

Fase 1 — n8n Decoupling (ANTES, aplicar correção AJ-1)
  └── CRÍTICO: adicionar guard em create_dispatch() antes de ligar o scheduler
  └── Risco zero para fluxo atual
  └── Estimativa: 1-2h de trabalho

Fase 2 — Banco / Modelo Editorial
  └── Criar tabela sources (necessária para Fase 3 funcionar completo)
  └── Criar tabela editorial_actions
  └── Migrações incrementais — risco baixo
  └── Estimativa: 2-4h

Fase 3 — Dashboard Cockpit
  └── Depende da Fase 2 para fontes gerenciáveis
  └── Pode iniciar antes da Fase 2 para partes que não usam sources
  └── Estimativa: 4-8h

Fase 4 — IA Assistida (melhorias UX)
  └── Independente, baixo risco
  └── Estimativa: 2-3h

Fase 5 — Clustering
  └── Feature nova, pode ir em paralelo com outras
  └── Maior esforço de implementação
  └── Estimativa: 6-12h

Fases 6, 7, 8, 9 — conforme tasks.md
```

**Nota sobre Fase 7 (Cards):** `card-editorial-base.html` existe mas não pode ser usado sem atualizar `card_renderer.py`. Implementar o suporte a múltiplos templates e novos placeholders antes de publicar o template.

---

## Conclusão

A base SDD é **apta para guiar a Fase 1** após as correções AJ-1, AJ-2 e AJ-3. As demais correções podem ser feitas de forma incremental antes das fases correspondentes.

Os problemas identificados não comprometem a visão geral nem as regras de preservação. O projeto real está bem refletido nos documentos. O n8n como camada auxiliar está corretamente posicionado. A IA assistida está bem delimitada e os riscos de regressão são gerenciáveis.

**Aprovado para Fase 1**, condicionado à correção do CRÍTICO-1 antes de ligar o scheduler interno.
