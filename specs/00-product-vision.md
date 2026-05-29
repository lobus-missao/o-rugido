# Spec 00 — Visão do Produto

**Status:** Aprovado
**Fase:** 0 — Diagnóstico e SDD

---

## Objetivo

Transformar o News Radar RSS em uma plataforma editorial moderna para captura, normalização, classificação, agrupamento, ranqueamento e produção de conteúdo visual baseado em notícias de interesse público: políticas, de transparência, de impacto social, polêmicas e graves.

---

## Público-Alvo

Redatores e editores de jornalismo digital com foco em Piauí, Teresina e Brasil. Profissionais que precisam:
- Monitorar muitas fontes de notícias com eficiência
- Identificar rapidamente o que é mais relevante
- Classificar editorialmente sem sobrecarga manual
- Gerar conteúdo visual (cards) de forma padronizada
- Aprovar e publicar com rastreabilidade

---

## Problema Resolvido

Sem a plataforma, o editor precisa:
1. Acessar manualmente dezenas de sites e RSS
2. Decidir importância de cada notícia sem critério objetivo
3. Produzir cards manualmente para cada publicação
4. Controlar o status de aprovação em planilhas ou memória
5. Depender de ferramentas externas (n8n) para automações básicas

Com a plataforma:
1. Notícias capturadas automaticamente de 57+ fontes
2. Score de relevância calculado automaticamente com IA assistida
3. Cards gerados a partir de templates padronizados
4. Fluxo de aprovação com histórico e rastreabilidade
5. Tudo controlável pela dashboard sem ferramentas extras

---

## Fluxo Editorial Desejado

```
1. Captura automática (RSS / APIs)
2. Normalização e deduplicação
3. Score automático inicial
4. Editor acessa dashboard → filtra por prioridade
5. Editor gera lote para IA → copia prompt → processa externamente
6. Editor cola JSON → sistema valida e importa
7. Scores atualizados → ranking refletido na dashboard
8. Editor seleciona artigos → agrupados por assunto quando relevante
9. Editor aprova artigo para edição
10. Sistema gera card PNG a partir do template
11. Editor aprova card → pronto para publicação
12. Publicação manual ou notificação via Telegram
```

---

## Módulos Principais

| Módulo | Descrição | Status atual |
|--------|-----------|--------------|
| Ingestão | RSS, APIs, scraping, manual | RSS funcional |
| Normalização | Limpeza de dados brutos | Funcional (básico) |
| Deduplicação | Por URL e título | Funcional |
| Agrupamento | Clustering por assunto | UI existe, backend incompleto |
| Ranking | Score multidimensional automático + IA | Funcional |
| IA Assistida | Prompt → JSON → importação | Funcional (fluxo manual) |
| Dashboard | Cockpit editorial central | Funcional, em expansão |
| Geração de Card | HTML template → PNG | Funcional |
| Aprovação | Fluxo editorial com estados | Funcional via Telegram |
| Publicação | Notificação e marcação | Manual |
| Auditoria | Histórico de ações | Básico (dispatch log) |

---

## Fora de Escopo (nesta fase)

- Chamadas automáticas a APIs de IA com custo
- Scraping de páginas com paywall ou login
- App mobile
- Multi-tenancy (múltiplas redações)
- API pública para consumidores externos
- Integração com CMS externo

---

## Critérios de Sucesso

1. Editor consegue operar o dia inteiro sem abrir n8n ou terminal
2. Notícias coletadas automaticamente a cada 30 minutos
3. ≥80% das notícias com score de IA em até 24h
4. Card gerado em menos de 30 segundos após aprovação
5. Histórico completo de quem aprovou/rejeitou cada item
6. Sistema funciona se n8n for desligado (fallback interno)
7. Nenhuma regra de negócio vive fora do código Python
