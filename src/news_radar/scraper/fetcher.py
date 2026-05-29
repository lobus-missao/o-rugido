"""Download de URLs com timeout, user-agent e tratamento de erro."""
from __future__ import annotations
import time
import traceback

import requests

from .models import FetchResult

USER_AGENT = "NewsRadarRSS/1.0 (editorial monitoring bot; +https://github.com/news-radar)"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]

_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": USER_AGENT})
    return _SESSION


def fetch_url(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    rate_limit: float = 1.0,
) -> FetchResult:
    """Baixa uma URL com retry e backoff. Nunca lança exceção."""
    session = _get_session()
    last_error: str | None = None

    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if rate_limit > 0 and attempt < retries - 1:
                time.sleep(rate_limit)
            return FetchResult(
                url=url,
                status_code=resp.status_code,
                html=resp.text,
            )
        except requests.exceptions.Timeout:
            last_error = f"Timeout após {timeout}s"
        except requests.exceptions.TooManyRedirects:
            last_error = "Redirecionamentos em excesso"
            break
        except requests.exceptions.ConnectionError as exc:
            last_error = f"Erro de conexão: {str(exc)[:200]}"
        except Exception as exc:
            last_error = f"Erro inesperado: {str(exc)[:200]}\n{traceback.format_exc(limit=1)}"
            break

        if attempt < retries - 1:
            time.sleep(RETRY_DELAYS[attempt])

    return FetchResult(url=url, error=last_error)
