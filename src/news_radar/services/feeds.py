"""Carregamento da configuração de feeds RSS (`configs/feeds.yaml`).

Mora aqui porque feeds.yaml descreve fontes de ingestão. Antes ficava em
`config.py`, mas era a única função com responsabilidade de domínio em um
módulo que deveria ser apenas constantes/paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from news_radar.core.config import FEEDS_PATH


def load_feeds_config(path: Path = FEEDS_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de feeds não encontrado: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("feeds", [])
    return data
