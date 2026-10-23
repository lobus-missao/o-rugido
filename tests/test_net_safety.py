"""SSRF: download de imagem só para hosts públicos, com redirects revalidados."""
from __future__ import annotations

import socket

import pytest

from o_rugido.core import net_safety
from o_rugido.core.net_safety import UnsafeURLError, assert_public_url, safe_get
from o_rugido.services import rendering

PUBLIC_IP = "93.184.216.34"


def _fake_dns(mapping: dict[str, list[str]]):
    def getaddrinfo(host, port, *a, **k):
        if host not in mapping:
            raise socket.gaierror("nao resolve")
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))
            for ip in mapping[host]
        ]

    return getaddrinfo


class _Resp:
    def __init__(self, status=200, location=None, content=b"ok"):
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.content = content
        self.is_redirect = status in (301, 302, 303, 307, 308) and bool(location)
        self.is_permanent_redirect = status in (301, 308) and bool(location)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "127.1.2.3", "10.0.0.5", "172.16.0.1", "192.168.1.10",
    "169.254.169.254",  # metadata de cloud
    "100.64.0.1",       # CGNAT
    "0.0.0.0", "224.0.0.1", "240.0.0.1",
    "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
])
def test_enderecos_nao_publicos_sao_bloqueados(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"alvo.test": [ip]}))
    with pytest.raises(UnsafeURLError):
        assert_public_url("http://alvo.test/img.png")


@pytest.mark.parametrize("ip", [PUBLIC_IP, "8.8.8.8", "2606:4700:4700::1111"])
def test_enderecos_publicos_passam(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [ip]}))
    assert_public_url("https://cdn.test/foto.jpg")


def test_um_endereco_privado_entre_varios_bloqueia(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"misto.test": [PUBLIC_IP, "10.0.0.9"]}))
    with pytest.raises(UnsafeURLError):
        assert_public_url("http://misto.test/x.png")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://cdn.test/a.png", "gopher://cdn.test/", "javascript:alert(1)",
    "data:image/png;base64,AAAA", "//cdn.test/a.png", "http:///sem-host", "",
])
def test_esquemas_e_urls_invalidas_sao_bloqueados(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)


def test_host_que_nao_resolve_e_bloqueado(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({}))
    with pytest.raises(UnsafeURLError):
        assert_public_url("http://inexistente.test/a.png")


def test_ip_literal_privado_na_url(monkeypatch):
    # sem DNS fake: o literal é resolvido localmente
    for url in ("http://127.0.0.1:8888/stats", "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/x", "http://10.1.2.3/x"):
        with pytest.raises(UnsafeURLError):
            assert_public_url(url)


class TestSafeGet:
    def test_resposta_normal(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        monkeypatch.setattr(net_safety.requests, "get", lambda url, **k: _Resp(200, content=b"img"))
        assert safe_get("https://cdn.test/a.png").content == b"img"

    def test_nunca_pede_redirect_automatico(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        seen = {}

        def fake_get(url, **kw):
            seen.update(kw)
            return _Resp(200)

        monkeypatch.setattr(net_safety.requests, "get", fake_get)
        safe_get("https://cdn.test/a.png")
        assert seen["allow_redirects"] is False

    def test_redirect_para_metadata_e_bloqueado(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        chamadas = []

        def fake_get(url, **kw):
            chamadas.append(url)
            return _Resp(302, location="http://169.254.169.254/latest/meta-data/")

        monkeypatch.setattr(net_safety.requests, "get", fake_get)
        with pytest.raises(UnsafeURLError):
            safe_get("https://cdn.test/a.png")
        assert chamadas == ["https://cdn.test/a.png"]  # o destino interno nunca foi consultado

    def test_redirect_relativo_publico_e_seguido(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        respostas = iter([_Resp(301, location="/outra/b.png"), _Resp(200, content=b"final")])
        urls = []

        def fake_get(url, **kw):
            urls.append(url)
            return next(respostas)

        monkeypatch.setattr(net_safety.requests, "get", fake_get)
        assert safe_get("https://cdn.test/a.png").content == b"final"
        assert urls == ["https://cdn.test/a.png", "https://cdn.test/outra/b.png"]

    def test_redirect_para_outro_host_publico_e_seguido(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"a.test": [PUBLIC_IP], "b.test": ["8.8.8.8"]}))
        respostas = iter([_Resp(302, location="https://b.test/x.jpg"), _Resp(200, content=b"b")])
        monkeypatch.setattr(net_safety.requests, "get", lambda url, **k: next(respostas))
        assert safe_get("https://a.test/x.jpg").content == b"b"

    def test_loop_de_redirects_e_cortado(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        monkeypatch.setattr(net_safety.requests, "get", lambda url, **k: _Resp(302, location="https://cdn.test/loop"))
        with pytest.raises(UnsafeURLError, match="redirects demais"):
            safe_get("https://cdn.test/a.png")

    def test_redirect_sem_location(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))
        resp = _Resp(302, location="x")
        resp.headers = {}
        monkeypatch.setattr(net_safety.requests, "get", lambda url, **k: resp)
        with pytest.raises(UnsafeURLError):
            safe_get("https://cdn.test/a.png")


class TestDownloadPostImage:
    def test_url_interna_nao_baixa_e_nao_levanta(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rendering, "CARDS_DIR", tmp_path)
        chamadas = []
        monkeypatch.setattr(net_safety.requests, "get", lambda *a, **k: chamadas.append(a))
        for url in ("http://127.0.0.1:8888/stats", "http://169.254.169.254/latest/meta-data/",
                    "http://o-rugido-app:8888/cards/x.png"):
            assert rendering.download_post_image(url, "abc123") is None
        assert chamadas == []
        assert list(tmp_path.iterdir()) == []

    def test_imagem_publica_continua_sendo_baixada(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rendering, "CARDS_DIR", tmp_path)
        monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({"cdn.test": [PUBLIC_IP]}))

        class Ok(_Resp):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.headers = {"Content-Type": "image/png"}

            def raise_for_status(self):
                pass

        monkeypatch.setattr(net_safety.requests, "get", lambda url, **k: Ok(200, content=b"\x89PNG"))
        dest = rendering.download_post_image("https://cdn.test/foto.png", "abc123")
        assert dest is not None
        assert dest.read_bytes() == b"\x89PNG"
        assert dest.suffix == ".png"
