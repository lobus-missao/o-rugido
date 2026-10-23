"""Proteção contra SSRF para downloads de URLs vindas de fora.

``safe_get`` só aceita http/https cujo host resolva apenas para endereços
públicos (bloqueia loopback, RFC1918, link-local/metadata, reservados) e
revalida cada redirecionamento.

Limitação conhecida: o DNS é resolvido na validação e de novo pelo
``requests`` na conexão; um DNS malicioso que troque a resposta entre as duas
(DNS rebinding) não é coberto. Para isso, restrinja a saída de rede do
container por firewall.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 5


class UnsafeURLError(ValueError):
    """URL não permitida (esquema inválido ou destino não público)."""


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_public_url(url: str) -> None:
    """Levanta UnsafeURLError se a URL não for http(s) para host público."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"esquema nao permitido: {parsed.scheme or '(vazio)'}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL sem host")
    try:
        infos = socket.getaddrinfo(host, parsed.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"host nao resolve: {host}") from exc
    if not infos:
        raise UnsafeURLError(f"host nao resolve: {host}")
    for info in infos:
        addr = info[4][0]
        if not _is_public_ip(addr):
            raise UnsafeURLError(f"destino nao publico: {host} -> {addr}")


def safe_get(
    url: str,
    *,
    timeout: float = 15,
    headers: dict[str, str] | None = None,
    max_redirects: int = _MAX_REDIRECTS,
) -> requests.Response:
    """GET que valida o destino (e cada redirect) antes de conectar."""
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        resp = requests.get(
            current, timeout=timeout, headers=headers, allow_redirects=False
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise UnsafeURLError("redirect sem Location")
            current = urljoin(current, location)
            continue
        return resp
    raise UnsafeURLError(f"redirects demais (> {max_redirects})")
