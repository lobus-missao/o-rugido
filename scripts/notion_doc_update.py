"""
Adiciona as secoes restantes da documentacao ao Notion via API direta.

Uso:
    1. Criar uma Notion Integration em https://www.notion.so/my-integrations
    2. Copiar o "Internal Integration Token" (começa com ntn_ ou secret_)
    3. Abrir a pagina do Notion (36e0fbbc...), clicar nos tres pontinhos > Connections > Add connection
    4. Adicionar a integracao criada
    5. Rodar:
        $env:NOTION_TOKEN="ntn_xxxx..."
        python scripts/notion_doc_update.py

A pagina alvo: https://www.notion.so/36e0fbbcfaa18135befbda291e815494
"""

import os
import sys
import json
import time
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
PARENT_PAGE_ID = "36e0fbbc-faa1-8135-befb-da291e815494"
API = "https://api.notion.com/v1"

if not NOTION_TOKEN:
    print("ERRO: Defina a variavel NOTION_TOKEN antes de rodar.")
    print("  $env:NOTION_TOKEN='ntn_xxxx...'")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def h1(text):
    return {"type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def h2(text):
    return {"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def h3(text):
    return {"type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def p(text, bold=False):
    annotations = {"bold": bold} if bold else {}
    return {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}, "annotations": annotations}]}}


def code(text, language="shell"):
    return {"type": "code", "code": {"rich_text": [{"type": "text", "text": {"content": text}}], "language": language}}


def bullet(text, bold_prefix=None):
    if bold_prefix:
        parts = [
            {"type": "text", "text": {"content": bold_prefix}, "annotations": {"bold": True}},
            {"type": "text", "text": {"content": text}},
        ]
    else:
        parts = [{"type": "text", "text": {"content": text}}]
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": parts}}


def divider():
    return {"type": "divider", "divider": {}}


def callout(text, emoji="⚠️"):
    return {
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def create_page(title, blocks, emoji=None):
    icon = {"type": "emoji", "emoji": emoji} if emoji else None
    body = {
        "parent": {"page_id": PARENT_PAGE_ID},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
        "children": blocks[:100],  # Notion limita 100 blocos por request
    }
    if icon:
        body["icon"] = icon

    r = requests.post(f"{API}/pages", headers=HEADERS, json=body)
    if r.status_code not in (200, 201):
        print(f"  ERRO {r.status_code}: {r.text[:300]}")
        return None
    return r.json()


def append_blocks(page_id, blocks):
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i+100]
        r = requests.patch(f"{API}/blocks/{page_id}/children", headers=HEADERS, json={"children": chunk})
        if r.status_code not in (200, 201):
            print(f"  ERRO append {r.status_code}: {r.text[:300]}")
        time.sleep(0.5)


# ── Pagina 1: Streamlit Dashboard ─────────────────────────────────────────────

def page_streamlit():
    blocks = [
        callout("Acesso: http://localhost:8501  |  Iniciar: streamlit run dashboard.py", "📊"),
        divider(),
        h2("Páginas disponíveis"),
        bullet("0 — Edições (0_Edicoes.py)", ""),
        p("  Acompanha morning/noon/evening do dia. Mostra status, artigo, card. Botão Marcar como publicado."),
        bullet("1 — Operação (1_Operacao.py)", ""),
        p("  Visão geral operacional: pipeline status, alertas ativos, dispatches pendentes."),
        bullet("2 — Lotes IA (2_Lotes_IA.py)", ""),
        p("  Gerencia enriquecimento por IA (Ollama). Cria lotes, envia, importa resultados JSON."),
        bullet("3 — Ranking (3_Ranking.py)", ""),
        p("  Top artigos por escopo (brasil/piaui/teresina), scores automáticos e IA."),
        bullet("4 — Clusters (4_Clusters.py)", ""),
        p("  Agrupa artigos por similaridade temática."),
        bullet("5 — Editorial (5_Editorial.py)", ""),
        p("  Status editorial: pending, approved, rejected, ready_to_publish, published."),
        bullet("6 — Entidades (6_Entidades.py)", ""),
        p("  Entidades extraídas dos artigos (pessoas, lugares, organizações)."),
        bullet("7 — Alertas (7_Alertas.py)", ""),
        p("  Alertas operacionais: dispatches travados, artigos sem ranking, feeds com falha."),
        bullet("8 — Fontes RSS (8_Fontes_RSS.py)", ""),
        p("  Lista e status de todos os feeds configurados em configs/feeds.yaml."),
        divider(),
        h2("Baixa manual — fluxo completo"),
        p("1. Abrir Edições (0_Edicoes.py)"),
        p("2. Selecionar a edição do dia (morning/noon/evening)"),
        p("3. Artigos com status ready_to_publish aparecem com botão Marcar como publicado"),
        p("4. Clicar no botão → status muda para published"),
        p("5. Alternativa via CLI: python -m news_radar.cli mark-published --dispatch-id 123"),
        divider(),
        h2("Verificar saúde do pipeline"),
        bullet("Alertas (7_Alertas.py) — mostra tudo que está travado ou faltando"),
        bullet("Ranking (3_Ranking.py) — confirmar que artigos novos entram com score"),
        bullet("Lotes IA (2_Lotes_IA.py) — status do enriquecimento por IA (opcional)"),
    ]
    return "📊 Streamlit Dashboard — 9 Páginas", blocks, "📊"


# ── Pagina 2: CLI ──────────────────────────────────────────────────────────────

def page_cli():
    blocks = [
        p("Todos os comandos usam o prefixo: python -m news_radar.cli"),
        divider(),
        h2("Sequência de operação básica"),
        code(
            "# 1. Criar schema (só na primeira vez)\n"
            "python -m news_radar.cli init-db\n\n"
            "# 2. Coletar feeds RSS\n"
            "python -m news_radar.cli collect --limit-per-feed 30\n\n"
            "# 3. Recalcular ranking\n"
            "python -m news_radar.cli rank\n\n"
            "# 4. Ver estatísticas\n"
            "python -m news_radar.cli stats\n\n"
            "# 5. Disparar edição (com Telegram)\n"
            "python -m news_radar.cli dispatch --edition morning --scope piaui --top 3\n\n"
            "# 5b. Disparar em dry-run (sem Telegram)\n"
            "python -m news_radar.cli dispatch --edition morning --scope piaui --top 3 --dry-run",
            "powershell"
        ),
        divider(),
        h2("Referência completa de comandos"),
        bullet("init-db — Cria/atualiza schema PostgreSQL"),
        bullet("collect --limit-per-feed N (default 30) — Coleta artigos dos feeds em configs/feeds.yaml"),
        bullet("rank — Recalcula auto_score e final_score para todos os artigos"),
        bullet("show --scope brasil|piaui|teresina --limit N — Exibe top artigos no terminal"),
        bullet("stats — Mostra contagens do banco (artigos, dispatches, lotes IA)"),
        bullet("dispatch --edition morning|noon|evening --scope X --top N --dry-run — Dispara top N ao Telegram"),
        bullet("mark-published --dispatch-id N — Marca dispatch como publicado (baixa manual)"),
        bullet("make-ai-batches --scope X --top N --batch-size N --days-back N — Gera lotes JSONL para Ollama"),
        bullet("list-ai-batches --limit N --status pending|running|completed|failed — Lista lotes de IA"),
        bullet("send-ai-batch --batch-id X --model X --timeout N — Envia lote para Ollama"),
        bullet("import-ai --file path.json --batch-id X — Importa resultado JSON de IA manualmente"),
        bullet("make-card --scope X --limit N — Gera cards PNG (uso direto, sem dispatch flow)"),
        bullet("telegram-webhook --action set|delete|info --url URL — Gerencia webhook Telegram"),
        bullet("cleanup --days N --expire-batches-hours N — Remove artigos velhos e expira lotes antigos"),
        divider(),
        h2("Exemplos úteis"),
        code(
            "# Ver top 10 do escopo piaui\n"
            "python -m news_radar.cli show --scope piaui --limit 10\n\n"
            "# Gerar lotes IA dos últimos 3 dias\n"
            "python -m news_radar.cli make-ai-batches --scope piaui --top 200 --days-back 3\n\n"
            "# Limpeza semanal\n"
            "python -m news_radar.cli cleanup --days 30 --expire-batches-hours 48\n\n"
            "# Marcar dispatch 123 como publicado\n"
            "python -m news_radar.cli mark-published --dispatch-id 123",
            "powershell"
        ),
    ]
    return "⌨️ CLI — Comandos Principais", blocks, "⌨️"


# ── Pagina 3: Variaveis de Ambiente ───────────────────────────────────────────

def page_env():
    blocks = [
        p("Copiar .env.example para .env e preencher antes de iniciar."),
        code("Copy-Item .env.example .env", "powershell"),
        divider(),
        h2("Variáveis obrigatórias"),
        bullet("DATABASE_URL — postgresql://news:senha@localhost:5432/news_radar — Conexão PostgreSQL principal"),
        bullet("POSTGRES_USER — news — Usuário do banco (usado pelo Docker)"),
        bullet("POSTGRES_PASSWORD — senha_segura_aqui — Senha do banco"),
        bullet("TELEGRAM_BOT_TOKEN — 123456:ABC-DEF... — Token do bot criado no @BotFather"),
        bullet("TELEGRAM_CHAT_ID — -100123456789 — ID do chat/grupo que recebe as mensagens"),
        divider(),
        h2("Variáveis opcionais"),
        bullet("OLLAMA_URL — http://host.docker.internal:11434 — URL do Ollama para IA local"),
        bullet("OLLAMA_MODEL — llama3.2 — Modelo Ollama para enriquecimento"),
        bullet("N8N_USER — admin — Login do painel n8n (produção)"),
        bullet("N8N_PASSWORD — (vazio) — Senha do painel n8n (produção)"),
        bullet("DOMAIN — news.seudominio.com.br — Domínio real para Caddy/HTTPS em produção"),
        bullet("NEWS_RADAR_API_URL — http://app:8888 — URL da API Python usada pelo n8n no Docker"),
        bullet("NEWS_RADAR_DRY_RUN — 0 — Se 1, nenhum envio Telegram é feito"),
        divider(),
        h2("Configuração para dev local"),
        code(
            "# .env — dev local\n"
            "DATABASE_URL=postgresql://news:senha@localhost:5432/news_radar\n"
            "POSTGRES_USER=news\n"
            "POSTGRES_PASSWORD=senha\n"
            "TELEGRAM_BOT_TOKEN=seu_token_aqui\n"
            "TELEGRAM_CHAT_ID=seu_chat_id_aqui\n"
            "OLLAMA_URL=http://localhost:11434\n"
            "OLLAMA_MODEL=llama3.2",
            "ini"
        ),
        h2("Configuração para produção (Docker)"),
        code(
            "# .env — produção\n"
            "DATABASE_URL=postgresql://news:senha_forte@db:5432/news_radar\n"
            "POSTGRES_USER=news\n"
            "POSTGRES_PASSWORD=senha_forte\n"
            "TELEGRAM_BOT_TOKEN=seu_token_aqui\n"
            "TELEGRAM_CHAT_ID=seu_chat_id_aqui\n"
            "N8N_USER=admin\n"
            "N8N_PASSWORD=senha_n8n_forte\n"
            "DOMAIN=news.seudominio.com.br\n"
            "NEWS_RADAR_API_URL=http://app:8888",
            "ini"
        ),
        divider(),
        h2("Segurança"),
        bullet("O arquivo .env está no .gitignore — nunca commitar"),
        bullet("Revogar e regenerar TELEGRAM_BOT_TOKEN se ele vazar"),
        bullet("Em produção, usar senhas fortes para POSTGRES_PASSWORD e N8N_PASSWORD"),
    ]
    return "🔧 Variáveis de Ambiente (.env)", blocks, "🔧"


# ── Pagina 4: Estrutura de Arquivos ───────────────────────────────────────────

def page_structure():
    tree = (
        "news_radar_rss/\n"
        "├── .env                          # Variáveis de ambiente (não versionado)\n"
        "├── .env.example                  # Template do .env\n"
        "├── Caddyfile                     # Config HTTPS reverso proxy (produção)\n"
        "├── Dockerfile                    # Imagem da API + CLI + Streamlit\n"
        "├── docker-compose.yml            # Stack completa de produção\n"
        "├── docker-compose.dev.yml        # Só PostgreSQL (dev local)\n"
        "├── start.ps1                     # Startup rápido dev local\n"
        "├── api_server.py                 # Flask API :8888\n"
        "├── dashboard.py                  # Streamlit entry point :8501\n"
        "├── pyproject.toml                # Dependências e configuração\n"
        "│\n"
        "├── configs/\n"
        "│   └── feeds.yaml                # Lista de fontes RSS com escopo e peso\n"
        "│\n"
        "├── data/\n"
        "│   ├── ai_batches/               # Lotes JSONL gerados para Ollama\n"
        "│   └── ai_results/               # Resultados JSON devolvidos pela IA\n"
        "│\n"
        "├── docs/\n"
        "│   ├── OPERACAO_EDITORIAL.md     # Playbook editorial\n"
        "│   └── N8N_WORKFLOWS.md          # Documentação dos workflows n8n\n"
        "│\n"
        "├── n8n/workflows/\n"
        "│   ├── 01_coleta.json            # Workflow coleta RSS (30min)\n"
        "│   └── 02_dispatch.json          # Workflow dispatch editorial (06:30/11:30/17:30)\n"
        "│\n"
        "├── pages/                        # Páginas Streamlit (sidebar)\n"
        "│   ├── 0_Edicoes.py\n"
        "│   ├── 1_Operacao.py\n"
        "│   ├── 2_Lotes_IA.py\n"
        "│   ├── 3_Ranking.py\n"
        "│   ├── 4_Clusters.py\n"
        "│   ├── 5_Editorial.py\n"
        "│   ├── 6_Entidades.py\n"
        "│   ├── 7_Alertas.py\n"
        "│   └── 8_Fontes_RSS.py\n"
        "│\n"
        "├── scripts/\n"
        "│   ├── telegram_poller.py        # Long-polling Telegram (Estratégia A)\n"
        "│   └── (outros scripts de manutenção)\n"
        "│\n"
        "├── src/news_radar/               # Pacote Python principal\n"
        "│   ├── cli.py                    # Comandos CLI\n"
        "│   ├── collector.py              # Coleta RSS\n"
        "│   ├── ranker.py                 # Scores automáticos\n"
        "│   ├── dispatch.py               # Fluxo editorial completo\n"
        "│   ├── telegram_sender.py        # Envio Telegram\n"
        "│   ├── card_renderer.py          # Geração de card PNG\n"
        "│   ├── ai_batches.py             # Lotes Ollama\n"
        "│   ├── repository.py             # Queries PostgreSQL\n"
        "│   └── db.py                     # Conexão e init do banco\n"
        "│\n"
        "├── templates/\n"
        "│   └── card.html                 # Template HTML do card PNG\n"
        "│\n"
        "└── tests/\n"
        "    ├── conftest.py               # Fixtures pytest\n"
        "    ├── test_api_smoke.py\n"
        "    ├── test_collector_smoke.py\n"
        "    ├── test_db_and_card_smoke.py\n"
        "    ├── test_dispatch_flow_smoke.py\n"
        "    └── test_ranking_and_ai_smoke.py"
    )
    blocks = [
        code(tree, "shell"),
        divider(),
        h2("Arquivos principais"),
        bullet("api_server.py — Flask API, ponte entre n8n e lógica Python. Porta 8888."),
        bullet("dashboard.py — Entry point do Streamlit. Porta 8501."),
        bullet("src/news_radar/dispatch.py — Lógica editorial completa (dispatch, approve, card, publish)"),
        bullet("src/news_radar/collector.py — Coleta RSS com feedparser"),
        bullet("src/news_radar/ranker.py — Calcula auto_score e final_score por escopo"),
        bullet("configs/feeds.yaml — Lista de fontes RSS com source_scope e source_trust"),
        bullet("scripts/telegram_poller.py — Long-polling getUpdates (Estratégia A, dev local)"),
    ]
    return "📁 Estrutura de Arquivos", blocks, "📁"


# ── Pagina 5: Testes ──────────────────────────────────────────────────────────

def page_tests():
    blocks = [
        p("O projeto usa pytest com smoke tests de integração."),
        code(
            "# Rodar todos os testes\npytest\n\n# Com output detalhado\npytest -v\n\n# Resultado esperado: 14 passed, 1 skipped",
            "powershell"
        ),
        divider(),
        h2("Suítes de teste"),
        bullet("test_api_smoke.py — Endpoints Flask: /health, /pipeline/collect, /pipeline/rank, /api/dispatch/run (dry_run), /api/dispatch/status"),
        bullet("test_collector_smoke.py — Coleta RSS: feedparser, deduplicação, inserção no banco"),
        bullet("test_db_and_card_smoke.py — Conexão com banco, init_db, geração de card PNG (Playwright)"),
        bullet("test_dispatch_flow_smoke.py — Fluxo editorial completo: create_dispatch → approve → generate_card → approve_card"),
        bullet("test_ranking_and_ai_smoke.py — Scoring automático, lotes IA, combine_with_ai"),
        divider(),
        h2("Pré-requisitos para rodar os testes"),
        code(
            "# PostgreSQL de teste rodando\ndocker compose -f docker-compose.dev.yml up -d\n\n"
            "# Chromium instalado (para card PNG)\nplaywright install chromium\n\n"
            "# .env preenchido (DATABASE_URL obrigatório)",
            "powershell"
        ),
        divider(),
        h2("O que está sendo skipped"),
        p("O teste skipped é o envio real ao Telegram — pulado quando TELEGRAM_BOT_TOKEN não está configurado ou NEWS_RADAR_DRY_RUN=1."),
        divider(),
        h2("Notas sobre os testes"),
        bullet("Todos os testes usam o banco real (não mock) — isolados via fixtures em conftest.py"),
        bullet("O conftest.py cria tabelas e faz cleanup após cada teste"),
        bullet("Testes de dispatch usam dry_run=True por padrão para não enviar ao Telegram"),
        bullet("Card PNG usa Playwright headless — requer Chromium instalado"),
    ]
    return "🧪 Testes", blocks, "🧪"


# ── Pagina 6: Deploy ──────────────────────────────────────────────────────────

def page_deploy():
    blocks = [
        h2("Pré-requisitos"),
        bullet("VPS Ubuntu 22.04+ com Docker + Docker Compose v2"),
        bullet("Domínio apontando para o IP do servidor (DNS propagado)"),
        bullet("Portas 80 e 443 abertas no firewall"),
        divider(),
        h2("Setup inicial"),
        code(
            "# 1. Clonar o repositório\ngit clone <repo_url> news_radar_rss\ncd news_radar_rss\n\n"
            "# 2. Criar .env de produção\ncp .env.example .env\nnano .env  # preencher todas as variáveis\n\n"
            "# 3. Subir stack completa\ndocker compose up -d\n\n"
            "# 4. Inicializar banco\ndocker compose exec app python -m news_radar.cli init-db\n\n"
            "# 5. Verificar saúde\ncurl http://localhost:8888/health",
            "shell"
        ),
        divider(),
        h2("Serviços e URLs após deploy"),
        bullet("Dashboard Streamlit — https://DOMAIN — Via Caddy (HTTPS automático)"),
        bullet("n8n — https://DOMAIN/n8n/ — Via Caddy (HTTPS automático)"),
        bullet("API Flask — http://app:8888 — Interno Docker (não exposto)"),
        bullet("PostgreSQL — db:5432 — Interno Docker (não exposto)"),
        divider(),
        h2("Configurar n8n em produção"),
        code(
            "# 1. Acessar n8n em https://DOMAIN/n8n/\n"
            "# 2. Settings → Variables:\n"
            "#    NEWS_RADAR_API = http://app:8888\n"
            "#    NEWS_RADAR_SCOPE = piaui\n"
            "# 3. Importar workflows: n8n/workflows/01_coleta.json e 02_dispatch.json\n"
            "# 4. Ativar ambos os workflows",
            "shell"
        ),
        divider(),
        h2("Telegram em produção — Estratégia B (Webhook)"),
        callout("NÃO rodar telegram_poller.py em produção quando o webhook estiver ativo.", "⚠️"),
        code(
            "# Registrar webhook\ndocker compose exec app python -c \"\n"
            "from news_radar.telegram_sender import set_webhook\n"
            "set_webhook('https://DOMAIN/webhook/telegram-approval')\n\"\n\n"
            "# Verificar\ndocker compose exec app python -c \"\n"
            "from news_radar.telegram_sender import get_webhook_info\n"
            "import json; print(json.dumps(get_webhook_info(), indent=2))\n\"",
            "shell"
        ),
        divider(),
        h2("Monitoramento"),
        code(
            "docker compose logs -f app    # Logs da API\n"
            "docker compose logs -f n8n    # Logs do n8n\n"
            "docker compose ps             # Status dos containers\n"
            "docker compose restart app    # Reiniciar um serviço",
            "shell"
        ),
        divider(),
        h2("Atualização do código"),
        code(
            "git pull\ndocker compose build app\ndocker compose up -d app\n"
            "# Se houver mudanças no schema:\ndocker compose exec app python -m news_radar.cli init-db",
            "shell"
        ),
        divider(),
        h2("Notas de segurança"),
        bullet("A API Flask (porta 8888) não está exposta publicamente — só acessível internamente via Docker network"),
        bullet("Caddy gerencia TLS/HTTPS automaticamente via Let's Encrypt"),
        bullet("O .env nunca deve ser commitado — está no .gitignore"),
        bullet("Trocar as senhas padrão do .env.example antes do deploy"),
    ]
    return "🚀 Deploy em Servidor", blocks, "🚀"


# ── Pagina 7: Checklists ──────────────────────────────────────────────────────

def page_checklists():
    blocks = [
        h2("Checklist — Dev Local (primeiro setup)"),
        h3("Infraestrutura"),
        bullet("Docker Desktop rodando"),
        bullet("docker compose -f docker-compose.dev.yml up -d — PostgreSQL no ar"),
        bullet(".env criado e preenchido (DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"),
        bullet(".venv ativo com pip install -e ."),
        bullet("playwright install chromium executado"),
        bullet("python -m news_radar.cli init-db — schema criado"),
        h3("Serviços rodando"),
        bullet("python api_server.py — responde em GET http://localhost:8888/health"),
        bullet("streamlit run dashboard.py — abre em http://localhost:8501"),
        bullet("npx n8n — abre em http://localhost:5678"),
        bullet("python scripts/telegram_poller.py — 'Aguardando callbacks...' no terminal"),
        h3("Coleta"),
        bullet("Workflow 01 ativo no n8n (ou POST /pipeline/collect manual)"),
        bullet("Artigos aparecem no Streamlit → Ranking"),
        bullet("Scores calculados (não zerados) no Ranking"),
        h3("Dispatch em dry-run"),
        bullet("POST /api/dispatch/run com \"dry_run\": true"),
        bullet("Resposta: {\"ok\": true, \"count\": 3, \"dry_run\": true}"),
        bullet("Dispatches aparecem no Streamlit → Edições"),
        bullet("NENHUMA mensagem chegou no Telegram"),
        h3("Dispatch real (fluxo completo)"),
        bullet("POST /api/dispatch/run com \"dry_run\": false"),
        bullet("3 mensagens chegam no Telegram com botões ✅/❌"),
        bullet("Clicar ✅ Aprovar em uma notícia"),
        bullet("Poller processa: dispatch_approve · dispatch X · por Nome"),
        bullet("Card PNG gerado e enviado ao Telegram"),
        bullet("Clicar ✅ Publicar no card"),
        bullet("Poller processa: card_approve · dispatch X · ready_to_publish"),
        bullet("Status ready_to_publish visível no Streamlit → Edições"),
        h3("Baixa manual"),
        bullet("Streamlit → Edições → botão Marcar como publicado"),
        bullet("Status muda para published"),
        divider(),
        h2("Checklist — Deploy Produção"),
        h3("DNS e servidor"),
        bullet("Domínio apontando para o IP do servidor (propagado)"),
        bullet("Portas 80 e 443 abertas no firewall"),
        bullet("Docker + Docker Compose v2 instalados"),
        h3("Configuração"),
        bullet(".env preenchido com senhas fortes e domínio real"),
        bullet("docker compose up -d — todos os containers no ar"),
        bullet("docker compose exec app python -m news_radar.cli init-db — schema OK"),
        bullet("curl https://DOMAIN/health — API respondendo"),
        bullet("https://DOMAIN — Dashboard Streamlit acessível"),
        bullet("https://DOMAIN/n8n/ — n8n acessível com login/senha"),
        h3("n8n em produção"),
        bullet("Variáveis: NEWS_RADAR_API=http://app:8888 e NEWS_RADAR_SCOPE=piaui"),
        bullet("Workflows 01_coleta e 02_dispatch importados e ativos"),
        bullet("Executar workflow 01 manualmente — verificar ok: true"),
        h3("Telegram em produção"),
        bullet("Webhook registrado: set_webhook('https://DOMAIN/webhook/telegram-approval')"),
        bullet("get_webhook_info() retorna url preenchida"),
        bullet("telegram_poller.py NÃO está rodando"),
        bullet("Dispatch real de teste — mensagens chegam e callbacks funcionam"),
        h3("Pós-deploy"),
        bullet("docker compose logs -f app — sem erros críticos"),
        bullet("Streamlit → Alertas — sem alertas vermelhos"),
        bullet("Fluxo completo de um dispatch real testado"),
    ]
    return "✅ Checklists de Validação", blocks, "✅"


# ── Main ──────────────────────────────────────────────────────────────────────

PAGES = [
    page_streamlit,
    page_cli,
    page_env,
    page_structure,
    page_tests,
    page_deploy,
    page_checklists,
]

print(f"Criando {len(PAGES)} sub-páginas em https://www.notion.so/{PARENT_PAGE_ID.replace('-', '')}\n")

for fn in PAGES:
    title, blocks, emoji = fn()
    print(f"  Criando: {title}...", end=" ", flush=True)
    result = create_page(title, blocks, emoji)
    if result:
        page_id = result.get("id", "")
        # Adicionar blocos restantes se houver mais de 100
        if len(blocks) > 100:
            append_blocks(page_id, blocks[100:])
        print(f"OK — {result.get('url', '')}")
    else:
        print("FALHOU")
    time.sleep(1)

print("\nConcluído.")
