"""
Reconstrói o workflow n8n — apenas o pipeline automático.
A aprovação Telegram fica no telegram_poller.py (já funciona).
"""
import sqlite3, json
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"
CRED_ID = "d02309d63d0c4d56"
CHAT_ID = "8773271293"

PYTHON = r"C:\Users\robep\Desktop\news_radar_rss\.venv\Scripts\python.exe"
CWD = r"C:\Users\robep\Desktop\news_radar_rss"


def code_node(node_id, name, cli_args, timeout_ms=60000, pos=None):
    js = f"""const {{ execSync }} = require('child_process');
const PYTHON = {json.dumps(PYTHON)};
const CWD = {json.dumps(CWD)};
try {{
  const out = execSync(
    `"${{PYTHON}}" -m news_radar.cli {cli_args}`,
    {{ cwd: CWD, timeout: {timeout_ms}, encoding: 'utf8' }}
  );
  try {{ return [{{ json: JSON.parse(out) }}]; }}
  catch {{ return [{{ json: {{ ok: true, output: out.trim().slice(0, 500) }} }}]; }}
}} catch(e) {{
  const msg = String(e.stderr || e.message || e).slice(0, 500);
  return [{{ json: {{ ok: false, error: msg }} }}];
}}"""
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos or [0, 300],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": js},
        "continueOnFail": True,
    }


def tg_send(node_id, name, text, pos=None):
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": pos or [0, 300],
        "credentials": {"telegramApi": {"id": CRED_ID, "name": "News Radar Telegram Bot"}},
        "parameters": {
            "resource": "message",
            "operation": "sendMessage",
            "chatId": CHAT_ID,
            "text": text,
            "additionalFields": {"parse_mode": "Markdown"},
        },
        "continueOnFail": True,
        "executeOnce": True,
    }


nodes = [
    # Schedule
    {
        "id": "schedule-trigger",
        "name": "A cada 2 horas",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.3,
        "position": [0, 300],
        "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 2}]}},
    },
    # Pipeline
    code_node("n-collect", "1. Coletar feeds",
              "collect --limit-per-feed 30", 120000, [240, 300]),
    code_node("n-rank", "2. Calcular ranking",
              "rank", 90000, [480, 300]),
    code_node("n-batch-br", "3a. Lotes Brasil",
              "make-ai-batches --scope brasil --top 200 --batch-size 30 --days-back 3",
              60000, [720, 200]),
    code_node("n-batch-pi", "3b. Lotes Piaui",
              "make-ai-batches --scope piaui --top 200 --batch-size 30 --days-back 3",
              60000, [720, 300]),
    code_node("n-batch-te", "3c. Lotes Teresina",
              "make-ai-batches --scope teresina --top 200 --batch-size 30 --days-back 3",
              60000, [720, 400]),
    # Notificação
    tg_send("n-notify", "4. Notificar lotes prontos",
            "*News Radar* - Ciclo concluido!\n\nLotes prontos para analise no dashboard.",
            [960, 300]),
    # Limpeza
    code_node("n-cleanup", "5. Limpeza",
              "cleanup --days 30 --expire-batches-hours 48",
              30000, [1200, 300]),
]

connections = {
    "A cada 2 horas":          {"main": [[{"node": "1. Coletar feeds",      "type": "main", "index": 0}]]},
    "1. Coletar feeds":        {"main": [[{"node": "2. Calcular ranking",    "type": "main", "index": 0}]]},
    "2. Calcular ranking":     {"main": [[
        {"node": "3a. Lotes Brasil",   "type": "main", "index": 0},
        {"node": "3b. Lotes Piaui",    "type": "main", "index": 0},
        {"node": "3c. Lotes Teresina", "type": "main", "index": 0},
    ]]},
    "3a. Lotes Brasil":        {"main": [[{"node": "4. Notificar lotes prontos", "type": "main", "index": 0}]]},
    "3b. Lotes Piaui":         {"main": [[{"node": "4. Notificar lotes prontos", "type": "main", "index": 0}]]},
    "3c. Lotes Teresina":      {"main": [[{"node": "4. Notificar lotes prontos", "type": "main", "index": 0}]]},
    "4. Notificar lotes prontos": {"main": [[{"node": "5. Limpeza", "type": "main", "index": 0}]]},
}

conn = sqlite3.connect(DB)
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
conn.execute(
    "UPDATE workflow_entity SET nodes=?, connections=?, active=1, updatedAt=? WHERE id=?",
    (json.dumps(nodes), json.dumps(connections), now, WORKFLOW_ID)
)
conn.commit()
conn.close()

print(f"Pipeline reconstruida com {len(nodes)} nos — sem Telegram Trigger.")
print("Aprovacao: telegram_poller.py (ja funciona e nao depende de n8n).")
print("Reinicie o n8n para ativar o schedule.")
