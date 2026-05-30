"""Hook PostToolUse: reinicia container Docker ao editar .py do projeto."""
import json
import subprocess
import sys

data = json.load(sys.stdin)
fp = data.get("tool_input", {}).get("file_path", "")
fp_unix = fp.replace("\\", "/")

if not fp.endswith(".py") or "news_radar_rss" not in fp_unix:
    sys.exit(0)

if "/pages/" in fp_unix or fp_unix.endswith("dashboard.py"):
    container = "news_radar_rss-dashboard-1"
elif "/src/" in fp_unix or fp_unix.endswith("api_server.py"):
    container = "news_radar_rss-app-1"
else:
    sys.exit(0)

filename = fp_unix.split("/")[-1]
print(f"Reiniciando {container} ({filename})...", flush=True)

r = subprocess.run(["docker", "restart", container], capture_output=True, text=True)
if r.returncode == 0:
    print(f"OK — {container} reiniciado.")
else:
    print(f"ERRO: {r.stderr.strip()[:200]}")
