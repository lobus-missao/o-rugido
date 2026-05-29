"""Tipos de dados compartilhados pelo pacote scraper."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FetchResult:
    url: str
    status_code: int | None = None
    html: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


@dataclass
class ExtractionResult:
    url: str
    strategy: str
    title: str | None = None
    content: str | None = None
    author: str | None = None
    date_str: str | None = None
    image_url: str | None = None
    extraction_quality: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.content)

    def quality_label(self) -> str:
        if self.extraction_quality >= 0.7:
            return "boa"
        if self.extraction_quality >= 0.4:
            return "razoável"
        if self.extraction_quality > 0:
            return "fraca"
        return "falhou"


@dataclass
class ScrapeRunStats:
    found: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_message: str | None = None
