"""Helper para chamar o MCP do n8n local."""
import json, sys, requests

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjNjY3YWEyYy02ZTNiLTQ1MzQtOTlhMi00YTU2NTA1NzhmZGQiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYzkwZmYyMTMtNThlYS00NDM1LTg0NzEtY2NhMTgzYTk2NWQyIiwiaWF0IjoxNzc5OTc2Njk3fQ.oYZ6tzdtA9LvzRqNH_tBS-MW7rx8zvvJwOyM5Z_S8Qw"
BASE = "http://localhost:5678/mcp-server/http"
REST = "http://localhost:5678/api/v1"


def rest(path, method="GET", **kwargs):
    """Chama a REST API do n8n diretamente."""
    r = requests.request(method, f"{REST}{path}",
        headers={"X-N8N-API-KEY": TOKEN}, timeout=15, **kwargs)
    return r.json()

def call(method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    r = requests.post(BASE, json=body, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }, timeout=30)
    for line in r.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return {}

def tool(name, **kwargs):
    return call("tools/call", {"name": name, "arguments": kwargs})

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "creds"

    if cmd == "creds":
        r = tool("list_credentials")
        for c in (r.get("result", {}).get("content") or [{}])[0].get("text", "[]") and json.loads((r.get("result", {}).get("content") or [{"text": "[]"}])[0]["text"]):
            print(f"  {c.get('id')} | {c.get('name')} | {c.get('type')}")

    elif cmd == "sdk":
        r = tool("get_sdk_reference")
        content = (r.get("result", {}).get("content") or [{}])[0].get("text", "")
        print(content[:3000])

    elif cmd == "nodes":
        query = sys.argv[2] if len(sys.argv) > 2 else "execute command"
        r = tool("search_nodes", query=query)
        content = (r.get("result", {}).get("content") or [{}])[0].get("text", "")
        print(content[:2000])

    elif cmd == "workflows":
        r = tool("search_workflows")
        content = (r.get("result", {}).get("content") or [{}])[0].get("text", "")
        print(content)
