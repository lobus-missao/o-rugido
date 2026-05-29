# Skill — Regras de Scraping (News Radar)

Referência para agentes implementando coleta de conteúdo.

---

## Hierarquia de Métodos

```
1. RSS via feedparser       → SEMPRE preferir quando disponível
2. API pública/gratuita     → quando RSS não existe mas API existe
3. requests + trafilatura   → HTML estático sem JS
4. Playwright              → apenas quando JS é necessário (último recurso)
5. Importação manual       → quando nenhuma automação é viável
```

---

## Quando Usar RSS (feedparser)

✅ Usar quando:
- Fonte tem feed RSS/Atom público
- URL de feed listada em `configs/feeds.yaml`
- Conteúdo é atualizado no feed (não apenas links)

```python
import feedparser
parsed = feedparser.parse(source["url"])
entries = parsed.entries[:limit_per_feed]
```

---

## Quando Usar API Pública

✅ Usar quando:
- Fonte tem API REST oficial e gratuita
- Chave de API disponível (configurada via `.env`)
- Termos de uso permitem uso editorial

```python
import requests
headers = {"User-Agent": "NewsRadarRSS/1.0 (editorial bot)"}
r = requests.get(url, headers=headers, timeout=30)
r.raise_for_status()
data = r.json()
```

---

## Quando Usar requests + trafilatura

✅ Usar quando:
- Fonte não tem RSS nem API
- Conteúdo HTML é estático (não requer JavaScript)
- Extração de texto limpo é suficiente

```python
import requests
import trafilatura

headers = {"User-Agent": "NewsRadarRSS/1.0 (editorial bot)"}
response = requests.get(url, headers=headers, timeout=30)

# Extração de texto limpo
text = trafilatura.extract(response.text)
# Ou metadados estruturados
metadata = trafilatura.extract_metadata(response.text)
```

---

## Quando Usar Playwright

✅ Usar apenas quando:
- JavaScript é necessário para renderizar o conteúdo
- Sem RSS, sem API, sem HTML estático
- Fonte é alta prioridade e vale o custo

❌ Não usar quando:
- Fonte tem RSS (desnecessário)
- Apenas para comodidade

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url, timeout=30000)
    content = page.content()
    browser.close()
```

---

## Rate Limiting

```python
import time

# Entre requisições do mesmo domínio
RATE_LIMIT = 1.0  # segundos mínimos

# Entre feeds diferentes
time.sleep(RATE_LIMIT)
```

---

## Timeout

```python
# Sempre configurar timeout
requests.get(url, timeout=30)  # 30 segundos
feedparser.parse(url)  # feedparser não tem timeout nativo — usar socket.setdefaulttimeout()
```

---

## Retries com Backoff

```python
import time

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]

for attempt in range(MAX_RETRIES):
    try:
        result = fetch_content(url)
        break
    except Exception as exc:
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAYS[attempt])
        else:
            raise  # propagar após esgotamento
```

---

## User-Agent

```python
HEADERS = {
    "User-Agent": "NewsRadarRSS/1.0 (editorial monitoring bot)"
}
```

Nunca simular User-Agent de browser real para burlar proteção.

---

## Salvar HTML/Texto Bruto

```python
# Útil para debug e reprocessamento
article["raw_html"] = response.text[:50000]  # truncar para não explodir banco
# ou salvar em arquivo referenciado no banco
```

---

## Logar Falhas

```python
# Em collector.py
try:
    parsed = feedparser.parse(source["url"])
except Exception as exc:
    status = "error"
    error = f"{exc}\n{traceback.format_exc(limit=2)}"
    result["errors"].append({"source": source.get("name"), "error": str(exc)})

# Sempre registrar em feed_runs
cur.execute("INSERT INTO feed_runs ... VALUES (%s, %s, %s, ...)",
            (source["name"], source["url"], status, ...))
```

---

## Restrições Absolutas

```
NÃO burlar:
- Captchas
- Login/autenticação de sites externos
- Paywalls
- Rate limits explícitos

NÃO armazenar:
- Senhas de sites externos
- Cookies de sessão de login
- Tokens de terceiros

NÃO extrair:
- Conteúdo pago sem autorização
- Dados pessoais de cidadãos individuais
- Conteúdo privado
```
