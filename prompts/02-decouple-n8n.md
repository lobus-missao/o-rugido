# Prompt 02 — Desacoplar n8n (Fase 1)

---

## Contexto

O News Radar RSS usa n8n apenas como scheduler HTTP:
- Workflow 01: a cada 30min → `POST /pipeline/collect` + `POST /pipeline/rank`
- Workflow 02: às 06:30/11:30/17:30 → `POST /api/dispatch/run`

Toda a lógica de negócio já está no Python. O n8n é apenas um agendador.

**Objetivo:** adicionar scheduler Python interno para eliminar a dependência do n8n como componente obrigatório.

---

## Spec de Referência

Leia: `specs/12-n8n-decoupling.md`

---

## O Que Implementar

### 1. Criar `src/news_radar/scheduler.py`

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(timezone="America/Fortaleza")
```

Jobs a adicionar:
- Coleta a cada 30min: `collect_feeds(limit_per_feed=30)`
- Dispatch morning às 06:30: `create_dispatch(edition="morning", scope="piaui", top=3)`
- Dispatch noon às 11:30
- Dispatch evening às 17:30

Ativar apenas se `NEWS_RADAR_SCHEDULER=1` no `.env`.

### 2. Integrar ao `api_server.py`

```python
import os
if os.getenv("NEWS_RADAR_SCHEDULER", "").lower() in {"1", "true"}:
    from news_radar.scheduler import scheduler
    scheduler.start()
```

### 3. Adicionar APScheduler ao `requirements.txt`

```
APScheduler>=3.10
```

### 4. Atualizar `.env.example`

```
# Scheduler interno (1=ativo, 0=usa n8n externo)
NEWS_RADAR_SCHEDULER=0
```

---

## Regras

1. Não quebrar workflows n8n existentes — endpoints da API permanecem
2. Scheduler é aditivo — não remove funcionalidade existente
3. `create_dispatch()` já é idempotente por data/edição
4. `collect_feeds()` já é idempotente por canonical_url
5. Não modificar lógica de coleta ou dispatch existente

---

## Validação

```bash
# Ativar scheduler
export NEWS_RADAR_SCHEDULER=1

# Verificar que jobs estão agendados
python -c "from news_radar.scheduler import scheduler; print(scheduler.get_jobs())"

# Testar coleta manual
python -m news_radar.cli collect --limit-per-feed 5

# Testar dispatch manual
python -m news_radar.cli dispatch --edition morning --scope piaui --dry-run

# Desligar n8n e confirmar que coleta continua
```

---

## Critérios de Aceite

- [ ] `scheduler.py` criado e funcional
- [ ] Ativação via variável de ambiente
- [ ] Jobs agendados corretamente (30min coleta, 3x/dia dispatch)
- [ ] n8n pode ser desligado sem impacto na coleta
- [ ] Testes smoke ainda passam
- [ ] `requirements.txt` atualizado
