from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse

STOPWORDS_PT = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sobre", "entre",
    "e", "ou", "que", "se", "ao", "aos", "à", "às", "é", "são", "foi", "ser",
    "mais", "menos", "após", "contra", "como", "diz", "dizem",
}


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return normalize_spaces(value)


def normalize_spaces(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def remove_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )


def normalize_text(value: str | None) -> str:
    value = normalize_spaces(value or "").lower()
    value = remove_accents(value)
    value = re.sub(r"[^a-z0-9\s$%-]", " ", value)
    value = normalize_spaces(value)
    return value


def title_signature(title: str) -> str:
    """
    Fingerprint do título para deduplicação cross-feed.
    Usa apenas as primeiras 10 palavras significativas ordenadas,
    para resistir a variações de ordem e sufixos ("- G1", "| CNN Brasil").
    """
    text = normalize_text(title)
    # Remove sufixos de fonte comuns ("- G1", "| Folha", etc.)
    text = re.sub(r"[-|]\s*\w[\w\s]{0,20}$", "", text).strip()
    tokens = sorted(t for t in text.split() if t not in STOPWORDS_PT and len(t) > 3)
    base = " ".join(tokens[:10])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16] if base else ""


# Parâmetros de tracking a remover da URL
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_name",
    "fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "twclid",
    "ref", "source", "via", "share", "from",
    "_ga", "_gid", "igshid", "s", "t",
}


def canonicalize_url(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()

    # Google News RSS envelopa o link real em parâmetros — desempacota
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("url", "u"):
        if query.get(key):
            candidate = unquote(query[key][0])
            if candidate.startswith("http"):
                url = candidate
                parsed = urlparse(url)
                break

    # Normaliza host: remove www. para unificar variantes
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    # Remove todos os parâmetros de tracking
    clean_query = []
    for k, vals in parse_qs(parsed.query).items():
        if k.lower() in _TRACKING_PARAMS or k.lower().startswith("utm_"):
            continue
        for v in vals:
            clean_query.append((k, v))

    query_str = "&".join(f"{k}={v}" for k, v in sorted(clean_query))
    normalized = parsed._replace(netloc=host, query=query_str, fragment="", scheme="https").geturl()
    return normalized.rstrip("/")


def article_id(url: str, title: str) -> str:
    base = canonicalize_url(url) or normalize_text(title)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def has_any(text: str, terms: list[str]) -> bool:
    norm = normalize_text(text)
    return any(normalize_text(term) in norm for term in terms)


def count_terms(text: str, terms: list[str]) -> int:
    norm = normalize_text(text)
    return sum(1 for term in terms if normalize_text(term) in norm)


def extract_money_values(text: str) -> list[str]:
    """Extrai valores monetários em reais do texto.

    Cobre variantes com e sem acento (bilhões/bilhoes, milhão/milhao).
    Usa \\b para evitar que 'mil' capture o prefixo de 'milhões'.
    Alternativa com multiplicador vem primeiro para capturar 'R$ 6,5 bilhões'
    completo antes de 'R$ 6' ser consumido pela alternativa numérica.
    """
    if not text:
        return []
    # Multiplicadores com e sem acento + word boundary para não pegar prefixo
    _mult = r"(?:trilh[õo]es?\b|bilh[õo]es?\b|bilh[aã]o\b|milh[õo]es?\b|milh[aã]o\b|mil\b)"
    pattern = (
        # Com multiplicador: R$ 6,5 bilhões / R$ 1,2 mil
        rf"R\$\s?\d+(?:[.,]\d+)?\s?{_mult}"
        r"|"
        # Número formatado: R$ 1.200.000,00 ou R$ 300,50
        r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?"
    )
    return re.findall(pattern, text, flags=re.IGNORECASE)
