# Spec 08 — Dashboard Editorial

**Status:** Em evolução
**Fase:** 3

---

## Princípio

A dashboard é o cockpit editorial. O editor deve conseguir operar o ciclo completo — coleta, ranking, IA, aprovação, publicação — sem abrir terminal, n8n ou Telegram.

---

## Módulos da Dashboard

### Radar (página principal — `dashboard.py`)

**O que mostra:**
- Métricas: total artigos, com IA, sem IA score alto, lotes pendentes, alertas
- Filtros: período, escopo, prioridade, status IA, busca por texto
- Artigos agrupados por prioridade (critica → alta → media → baixa → ruido)
- Cartão por artigo com ações rápidas

**Ações disponíveis por artigo:**
- Ver detalhes
- Marcar como needs_ai
- Selecionar para edição
- Rejeitar / arquivar

### Edições (`0_Edicoes.py`)

**O que mostra:**
- Dispatches do dia por edição (morning / noon / evening)
- Status de cada dispatch: pending_article → article_approved → pending_card → ready_to_publish → published
- Artigo, score, prioridade, fonte, data de publicação
- Ações: aprovar artigo, rejeitar artigo, gerar card, aprovar card, rejeitar card, marcar publicado

**Ações disponíveis:**
- `dispatch.approve_article(dispatch_id, user)` → aprova artigo e gera card
- `dispatch.reject_article(dispatch_id, user)` → rejeita artigo
- `dispatch.approve_card(dispatch_id, user)` → aprova card
- `dispatch.reject_card(dispatch_id, user)` → rejeita card
- `dispatch.regenerate_card(dispatch_id, user)` → regera card
- `dispatch.mark_published(dispatch_id)` → marca como publicado
- `dispatch.create_dispatch(edition, scope, top)` → cria nova edição

### Operação (`1_Operacao.py`)

**O que mostra:**
- Saúde do pipeline: total artigos, coletas recentes, erros por fonte
- Métricas de cards: total, aprovados, rejeitados, aguardando Telegram
- Log de coletas recentes (tabela com filtro por status)

**Ações disponíveis:**
- Coletar feeds (CLI: `collect --limit-per-feed 30`)
- Recalcular ranking (CLI: `rank`)
- Gerar lotes IA (CLI: `make-ai-batches`)
- Limpeza (CLI: `cleanup`)

**Futuros:**
- Gerenciar fontes RSS (CRUD quando tabela `sources` implementada)
- Configurar agendamento (scheduler interno)

### Lotes de IA (`2_Lotes_IA.py`)

**O que mostra:**
- Cobertura de IA: percentual por escopo, barras de progresso
- Lotes pendentes com prompt para copiar
- Textarea para colar resposta JSON
- Validação em tempo real da resposta
- Histórico de lotes concluídos e falhados

**Ações disponíveis:**
- Gerar novo lote (com parâmetros: escopo, período, tamanho)
- Copiar prompt para clipboard
- Colar e validar JSON
- Importar resultado

### Ranking (`3_Ranking.py`)

**O que mostra:**
- Tabela de artigos ordenados por score final
- Filtros: escopo, prioridade, período, status IA, status editorial
- Scores auto, ai, final por artigo
- Motivos do score (score_reasons_json)

### Clusters (`4_Clusters.py`)

**O que mostra (futuro — Fase 5):**
- Grupos de notícias sobre o mesmo assunto
- Score agregado por cluster, contagem de fontes
- Artigos do cluster com indicação do primário

**Ações:**
- Marcar artigo primário
- Mesclar clusters
- Arquivar cluster

### Mesa Editorial (`5_Editorial.py`)

**O que mostra:**
- Fila de artigos para ação editorial
- Filtro por status: needs_ai, ai_done, selected, etc.
- Detalhes do artigo no painel lateral

**Ações:**
- Aprovar para edição
- Rejeitar
- Selecionar para lote IA
- Alterar prioridade manualmente
- Gerar card

### Entidades (`6_Entidades.py`)

**O que mostra:**
- Entidades mais mencionadas (extraídas pela IA)
- Artigos por entidade
- Frequência por período

### Alertas (`7_Alertas.py`)

**O que mostra:**
- Alertas editoriais: artigos críticos sem IA, fontes com erro, etc.
- Severidade: critica, alta, media
- Ação recomendada para cada alerta

### Fontes RSS (`8_Fontes_RSS.py`)

**O que mostra:**
- Lista de fontes configuradas
- Status: ativa, erro, desabilitada
- Última coleta e contagem

**Futuros:**
- Adicionar nova fonte via formulário
- Habilitar/desabilitar fonte
- Testar feed antes de salvar

---

## Padrões de Interface

### Filtros
- Sempre no topo da página
- Persistir via `st.session_state` quando necessário
- Defaults razoáveis (últimas 24h, escopo brasil, prioridade alta+critica)

### Tabelas
- Usar `st.dataframe()` para dados densos
- Usar cards customizados `article_card()` para dados editoriais
- Ordenar por relevância por padrão

### Ações
- Botões com rótulos explícitos: "▶ Coletar feeds", "✅ Aprovar", "❌ Rejeitar"
- Spinner durante operações longas
- Mensagem de sucesso/erro após ação
- Confirmação para ações destrutivas: `st.warning + st.button("Confirmar")`

### Status Editoriais (cores)
```python
PRIORITY_COLOR = {
    "critica": "#dc2626",
    "alta": "#ea580c",
    "media": "#d97706",
    "baixa": "#16a34a",
    "ruido": "#6b7280",
}
```

### Feedback Visual
- `st.success()` após ação bem-sucedida
- `st.error()` com mensagem descritiva após falha
- `st.warning()` para alertas não bloqueantes
- `st.spinner()` para operações longas

---

## Critérios de Aceite

- [ ] Editor consegue operar ciclo completo sem abrir terminal
- [ ] Cada página tem filtros funcionais
- [ ] Ações de aprovação/rejeição refletem imediatamente na tabela
- [ ] Erros são exibidos com mensagem descritiva
- [ ] Dashboard funciona com banco vazio sem crash
- [ ] Cada página carrega em menos de 5 segundos com 10k artigos
