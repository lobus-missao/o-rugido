# Prompt 01 — Bootstrap: Entender e Planejar

Use este prompt ao iniciar uma nova sessão de trabalho no News Radar RSS.

---

## Instruções para o Agente

Você vai trabalhar no projeto News Radar RSS. Antes de qualquer implementação, leia e absorva o contexto:

**1. Leia estes arquivos obrigatoriamente:**
- `AGENTS.md` — regras gerais, papéis, restrições
- `docs/project-audit.md` — diagnóstico completo do projeto atual
- `docs/target-architecture.md` — onde queremos chegar
- `tasks.md` — backlog por fases

**2. Identifique em qual fase estamos trabalhando** (ver `tasks.md`).

**3. Leia a spec da fase:**
- `specs/12-n8n-decoupling.md` se for Fase 1
- `specs/08-editorial-dashboard.md` se for Fase 3
- etc.

**4. Leia os arquivos de código relevantes** antes de qualquer mudança.

**5. Confirme entendimento:** descreva em 3-5 linhas o que o projeto faz hoje e o que a fase atual precisa entregar.

**6. Crie um plano incremental** com etapas claras antes de implementar.

---

## Regras para Esta Sessão

- Não altere comportamento funcional existente
- Não mova arquivos sem justificativa
- Comece pelo desacoplamento do n8n (Fase 1) se ainda não foi feito
- Cada mudança deve ser testável e reversível
- Pergunte antes de fazer operações destrutivas

---

## Estrutura do Projeto (Referência Rápida)

```
src/news_radar/
  config.py         → paths, env vars
  db.py             → schema + connect()
  collector.py      → RSS → banco
  ranker.py         → scoring
  repository.py     → queries de leitura
  ai_batches.py     → lotes de IA
  card_renderer.py  → HTML → PNG
  dispatch.py       → fluxo editorial
  cli.py            → CLI argparse
api_server.py       → Flask porta 8888
dashboard.py        → Streamlit main
pages/              → páginas do dashboard
configs/feeds.yaml  → 57 feeds RSS
templates/card.html → template de card
data/               → arquivos gerados
```

---

## Validação Rápida do Ambiente

```bash
# Verificar banco
python -m news_radar.cli stats

# Verificar API
curl http://localhost:8888/health

# Verificar Streamlit
# streamlit run dashboard.py

# Rodar testes smoke
python -m pytest tests/ -v
```
