# Checklist de Validação End-to-End — News Radar RSS

> Validação manual completa do fluxo editorial, do zero até a publicação.
> Execute este checklist após cada deploy ou grande atualização.

---

## 0. Infraestrutura

- [ ] `docker compose ps` — todos os containers `running` (ou `healthy`)
- [ ] `curl http://localhost:8888/health` → `{"status": "ok"}`
- [ ] Dashboard abre em `http://localhost:8501` sem traceback
- [ ] `curl http://localhost:8888/api/scheduler/status` responde JSON
- [ ] Banco acessível: `python -m news_radar.cli stats` retorna dados

---

## 1. Coleta RSS

```bash
python -m news_radar.cli collect --limit-per-feed 5
```

- [ ] Comando retorna JSON com `ok: true`
- [ ] `inserted` > 0 (ou `duplicates` se feeds já coletados)
- [ ] Na dashboard → Operação: coleta recente aparece no log
- [ ] Fontes sem erro no log de coletas

---

## 2. Ranking automático

```bash
python -m news_radar.cli rank
```

- [ ] Retorna `"Ranking recalculado para N noticias."`
- [ ] Dashboard → Radar: artigos com `final_score_brasil > 0` aparecem
- [ ] Dashboard → Ranking: artigos ordenados por score
- [ ] Score de artigo de Teresina > score de artigo nacional genérico (no escopo Teresina)

---

## 3. IA assistida manual

Na dashboard → Lotes IA:

- [ ] Botão "Gerar lote" cria arquivo em `data/ai_batches/`
- [ ] Prompt visível com botão de cópia
- [ ] Métricas do lote exibidas (tokens estimados, artigos)
- [ ] Colar JSON válido → validação OK → botão "Importar" habilitado
- [ ] Após importar: artigos com `ai_score` aparecem com badge "IA"
- [ ] JSON inválido → erro amigável sem crash

---

## 4. Clustering

```bash
python -m news_radar.cli cluster-articles --hours 72 --scope piaui
```

- [ ] Retorna JSON com `clusters_created` ou `clusters_updated`
- [ ] Dashboard → Clusters (aba banco): clusters aparecem com contagem de fontes
- [ ] Ação "Definir artigo primário" funciona sem erro
- [ ] Ação "Arquivar cluster" funciona sem erro

---

## 5. Geração de card

Na dashboard → Editorial → Gerar Card:

- [ ] Selectbox de artigos preenchido
- [ ] Título e subtítulo pré-preenchidos com sugestões da IA (quando disponível)
- [ ] Botão "Preview HTML" mostra card renderizado sem placeholder `{{...}}` visível
- [ ] Arquivo HTML salvo em `data/cards/*.html`
- [ ] Se Playwright disponível: PNG salvo em `data/cards/*.png`
- [ ] Se Playwright ausente: aviso claro, sem crash

Teste alternativo via CLI:
```bash
python -m news_radar.cli make-card --scope piaui --limit 1
```

- [ ] Retorna JSON com `card_path` ou erro de Playwright documentado

---

## 6. Fluxo de aprovação via dashboard

Na dashboard → Edições:

- [ ] Botão "Disparar agora" cria dispatch (dry-run para teste):
  ```python
  from news_radar.dispatch import create_dispatch
  create_dispatch("morning", scope="piaui", top=1, dry_run=True)
  ```
- [ ] Dispatch aparece na página de Edições com status `pending_article`
- [ ] Botão "Aprovar artigo" → status muda para `article_approved`
- [ ] Botão "Rejeitar" → status muda para `article_rejected`
- [ ] Campo "Nota do revisor" aceita texto e persiste no dispatch
- [ ] Histórico de ações aparece no expander por dispatch

---

## 7. Aprovação de card

Continuando o fluxo acima após aprovação do artigo:

- [ ] Se Playwright disponível: card PNG gerado automaticamente, aparece preview
- [ ] Botão "Aprovar card" → status `ready_to_publish`
- [ ] Botão "Rejeitar card" → status `card_rejected`
- [ ] Botão "Regerar card" → novo card gerado

---

## 8. Publicação manual

- [ ] Botão "Marcar como publicado" → status `published`
- [ ] Artigo na página Radar mostra `editorial_status = published`

---

## 9. Auditoria editorial

Na dashboard → Auditoria:

- [ ] Página carrega sem traceback
- [ ] Métricas exibem totais corretos (aprovações, rejeições, publicações)
- [ ] Filtro por tipo de ação funciona
- [ ] Filtro por ator funciona
- [ ] Busca por artigo ID retorna histórico correto

---

## 10. Integridade do banco

```bash
python -m news_radar.cli stats
```

- [ ] JSON retorna sem erro
- [ ] `total_articles` > 0
- [ ] `articles_with_ai` ≥ 0

```sql
-- Verificar tabela schema_migrations (Fase 9)
SELECT id, applied_at FROM schema_migrations ORDER BY applied_at;
-- Deve listar todas as migrations aplicadas
```

---

## 11. Performance básica

- [ ] Dashboard → Radar carrega em < 5s
- [ ] Dashboard → Clustering carrega em < 10s
- [ ] `collect` completo < 3min para 57 feeds
- [ ] `rank` < 30s para até 10k artigos

---

## 12. Backup

```bash
python -m news_radar.cli backup --output /tmp/test_backup.sql
```

- [ ] Arquivo gerado com tamanho > 0
- [ ] Ou: mensagem clara de que pg_dump não está disponível com instrução alternativa

---

## Resultado esperado

Todos os checkboxes marcados = sistema pronto para operação em produção.

Se algum item falhar, consultar:
- [docs/OPERATIONS.md](OPERATIONS.md) — resolução de problemas
- [docs/DEPLOYMENT.md](DEPLOYMENT.md) — configuração e deploy
