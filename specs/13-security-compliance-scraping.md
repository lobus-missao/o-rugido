# Spec 13 — Segurança, Compliance e Scraping Responsável

**Status:** Aprovado
**Fase:** 0 — Aplicar em todas as fases

---

## Scraping Responsável

### Quando Usar RSS
- **Sempre que disponível.** RSS é o canal oficial de distribuição de conteúdo.
- Feedparser já implementa corretamente.
- 57 feeds configurados usam RSS.

### Quando Usar API Pública
- Quando fonte oferece API oficial (mesmo gratuita).
- Verificar termos de uso antes de integrar.
- Usar chave de API (nunca hardcoded — sempre via `.env`).

### Quando Usar requests + trafilatura
- Fonte não tem RSS nem API.
- Conteúdo é HTML estático (não requer JavaScript).
- `trafilatura` extrai texto limpo sem depender de seletores frágeis.

### Quando Usar Playwright
- Apenas quando JavaScript é necessário para carregar conteúdo.
- Custo alto: navegador completo, mais memória, mais lento.
- Limitar a no máximo 5 fontes simultâneas.
- Nunca para fontes que têm RSS disponível.

---

## Restrições de Scraping

```
NÃO burlar:
- robots.txt (verificar e respeitar quando aplicável)
- Login / autenticação (nunca armazenar credenciais de sites externos)
- Paywall (não extrair conteúdo pago)
- Captcha (não usar solvers)
- Rate limits explicitados pelo site

NÃO fazer:
- Requisições paralelas agressivas ao mesmo domínio
- Scraping de dados pessoais de cidadãos
- Armazenar senhas ou tokens de terceiros no banco
```

---

## Rate Limiting

```python
# Padrão mínimo entre requisições para o mesmo domínio
RATE_LIMIT_SECONDS = 1.0

# Timeout para cada requisição
REQUEST_TIMEOUT_SECONDS = 30

# Retry com backoff
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]  # segundos
```

---

## User-Agent

```python
# Identificável — não simular browser real para burlar proteção
HEADERS = {
    "User-Agent": "NewsRadarRSS/1.0 (+https://github.com/SEU_REPO; editorial bot)"
}
```

---

## Sanitização

### HTML
```python
# Já implementado em text_utils.strip_html()
# Nunca retornar HTML bruto do feed diretamente ao usuário sem sanitização
from bs4 import BeautifulSoup
text = BeautifulSoup(html, "html.parser").get_text()
```

### Dados da IA
```python
# Nunca confiar cegamente no JSON da IA
# Validar schema antes de importar
# Rejeitar campos desconhecidos com log
# Validar tipos: numérico onde esperado numérico
for field in ["interesse_publico", "impacto_social", "urgencia"]:
    value = item.get(field, 0)
    if not isinstance(value, (int, float)):
        value = 0  # fallback seguro
```

### Payload da API
```python
# Nunca executar código vindo de payloads externos
# Validar tipos e tamanhos antes de processar
# Nunca usar eval() ou exec() com dados externos
```

---

## Proteção de Credenciais

### O que vai em `.env` (nunca em código)
```
DATABASE_URL=postgresql://...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OLLAMA_URL=http://...
N8N_USER=...
N8N_PASSWORD=...
```

### .gitignore
```
.env
.env.*
!.env.example
data/cards/*.png
data/ai_batches/*.json
data/ai_results/*.json
```

### Verificação
```bash
# Nunca comitar .env
git status --short | grep -v "^?" | grep -E "\.(env|key|pem)"
```

---

## Validação de Payload IA

```python
# Exemplo de validação mínima antes de importar
REQUIRED_ID_FIELD = "id"
NUMERIC_FIELDS = ["interesse_publico", "impacto_social", "urgencia",
                  "relevancia_local", "dinheiro_publico"]

def validate_ai_item(item: dict) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, "item não é dict"
    if not item.get(REQUIRED_ID_FIELD):
        return False, "campo 'id' ausente"
    for field in NUMERIC_FIELDS:
        if field in item:
            try:
                float(item[field])
            except (TypeError, ValueError):
                return False, f"campo '{field}' não é numérico"
    return True, ""
```

---

## Proteção Contra JSON Inválido

```python
# ai_batches.py — já implementado
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    raise ValueError(f"JSON inválido: {e}")
```

Sempre exibir erro antes de importar:
```python
# pages/2_Lotes_IA.py — já implementado
if not validation["ok"]:
    st.error(f"❌ {validation['error']}")
    # botão de importar permanece desabilitado
```

---

## Logs Sem Dados Sensíveis

```python
# Nunca logar:
# - tokens de API
# - senhas
# - conteúdo completo de artigos pagos
# - dados pessoais de fontes

# Logar apenas:
# - source name (não URL completa com credenciais)
# - status (ok/error)
# - contagens
# - mensagens de erro truncadas
error_log = str(exc)[:500]  # truncado
```

---

## Segurança da API Flask

- Porta 8888 não deve ser exposta publicamente sem autenticação
- Em produção: expor apenas via Caddy com HTTPS
- Validar todos os parâmetros de entrada
- Não executar comandos arbitrários via parâmetros
- `subprocess.run(CLI + list(args))` — `args` vem de campos validados, não de user input diretamente

---

## Critérios de Aceite

- [ ] `.env` nunca commitado (`.gitignore` configurado)
- [ ] Credenciais em variáveis de ambiente, nunca hardcoded
- [ ] HTML de feeds sanitizado antes de salvar
- [ ] JSON da IA validado antes de importar
- [ ] Logs não contêm tokens ou senhas
- [ ] Timeout configurado em todas as requisições HTTP externas
- [ ] Scraping respeitando rate limit mínimo de 1s por domínio
