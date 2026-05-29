# Spec 12 — Desacoplamento do n8n

**Status:** Em planejamento
**Fase:** 1

---

## Diagnóstico de Uso Atual do n8n

### O que n8n faz hoje

| Workflow | Trigger | Ação | Endpoint |
|----------|---------|------|----------|
| 01_coleta | Cron a cada 30min | POST /pipeline/collect + POST /pipeline/rank | api_server.py |
| 02_dispatch | Cron 06:30 / 11:30 / 17:30 | POST /api/dispatch/run | api_server.py |

### O que n8n NÃO faz (correto)

- Não contém lógica de seleção de artigos
- Não calcula scores
- Não controla estados editoriais
- Não processa callbacks do Telegram (usa telegram_poller.py)

### Dependência Atual

Se n8n cair:
- ❌ Coleta RSS para (artigos não são atualizados)
- ❌ Dispatch editorial para (edições não são disparadas automaticamente)
- ✅ Dashboard continua funcionando
- ✅ Importação de IA continua funcionando
- ✅ Telegram continua funcionando (via poller)

---

## O Que Pode Continuar no n8n

Após o desacoplamento, n8n pode opcionalmente continuar como:

| Uso | Tipo | Prioridade |
|-----|------|-----------|
| Agendamento de coleta (via HTTP) | Trigger externo | Baixa (substituído) |
| Agendamento de dispatch (via HTTP) | Trigger externo | Baixa (substituído) |
| Webhook Telegram para produção | Relay de webhooks | Média |
| Notificações para Slack/email | Automação extra | Baixa |
| Integrações futuras | Automação extra | Baixa |

---

## O Que Deve Sair do n8n

| O que sair | Para onde vai |
|-----------|--------------|
| Agendamento de coleta | APScheduler interno no Python |
| Agendamento de dispatch | APScheduler interno no Python |
| Dependência obrigatória | n8n vira componente opcional |

---

## Plano Incremental de Desacoplamento

### Etapa 1.1 — Scheduler Interno (APScheduler)

Criar `src/news_radar/scheduler.py`:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from .collector import collect_feeds
from .dispatch import create_dispatch

scheduler = BackgroundScheduler(timezone="America/Fortaleza")

# Coleta a cada 30 minutos
scheduler.add_job(
    lambda: collect_feeds(limit_per_feed=30),
    "interval", minutes=30, id="collect_feeds"
)

# Dispatch editorial
scheduler.add_job(
    lambda: create_dispatch(edition="morning", scope="piaui", top=3),
    "cron", hour=6, minute=30, id="dispatch_morning"
)
scheduler.add_job(
    lambda: create_dispatch(edition="noon", scope="piaui", top=3),
    "cron", hour=11, minute=30, id="dispatch_noon"
)
scheduler.add_job(
    lambda: create_dispatch(edition="evening", scope="piaui", top=3),
    "cron", hour=17, minute=30, id="dispatch_evening"
)
```

### Etapa 1.2 — Inicialização Condicional

Variável de ambiente `NEWS_RADAR_SCHEDULER=1` para ativar scheduler interno.
Quando ativo, n8n pode ser desligado sem impacto.

```python
# api_server.py ou script de start
import os
if os.getenv("NEWS_RADAR_SCHEDULER", "").lower() in {"1", "true"}:
    from news_radar.scheduler import scheduler
    scheduler.start()
```

### Etapa 1.3 — Dashboard de Scheduler (futuro)

Página `1_Operacao.py` pode exibir:
- Status do scheduler (ativo/inativo)
- Próximas execuções agendadas
- Histórico de execuções do scheduler
- Botão para forçar execução imediata

### Etapa 1.4 — Documentar como Opcional

Atualizar `docker-compose.yml` para tornar n8n service opcional:
```yaml
n8n:
  profiles: ["n8n"]  # só sobe com --profile n8n
```

---

## Endpoints Necessários (Já Existem)

| Endpoint | Método | Função |
|----------|--------|--------|
| `/pipeline/collect` | POST | Coletar feeds |
| `/pipeline/rank` | POST | Recalcular ranking |
| `/api/dispatch/run` | POST | Criar dispatch editorial |
| `/health` | GET | Verificar se API está ativa |

Estes endpoints continuam existindo para que n8n possa chamar caso ainda seja usado.

---

## Compatibilidade Durante Transição

**Fase de transição:**
1. Scheduler interno ativo (`NEWS_RADAR_SCHEDULER=1`)
2. n8n também ativo
3. n8n workflows desabilitados (não deletados)
4. Monitorar: ambos não devem disparar ao mesmo tempo

**Prevenção de duplo disparo:**
- `create_dispatch()` verifica se já existe dispatch para a edição/data antes de criar
- `collect_feeds()` é idempotente por canonical_url
- Dispatcher com retry não causa duplicatas

**Rollback:**
- Para voltar ao n8n: desabilitar scheduler (`NEWS_RADAR_SCHEDULER=0`)
- Reativar workflows n8n

---

## Estratégia de Fallback

```
Se scheduler Python falhar:
1. Dashboard alerta: "Scheduler inativo — última coleta há Xh"
2. Editor pode disparar coleta manual pelo dashboard
3. Editor pode criar dispatch manual pelo dashboard
4. n8n pode ser reativado como fallback de emergência
```

---

## Critérios de Aceite

- [ ] Coleta RSS funciona sem n8n rodando (scheduler interno)
- [ ] Dispatch editorial dispara 3x/dia sem n8n
- [ ] Dashboard mostra status do scheduler
- [ ] n8n pode ser desligado sem alertas críticos
- [ ] Reativar n8n não causa duplicatas
- [ ] Todas as operações também funcionam via dashboard (manual)
