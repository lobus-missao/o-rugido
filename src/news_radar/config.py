from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "configs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
FEEDS_PATH = CONFIG_DIR / "feeds.yaml"
AI_BATCHES_DIR = DATA_DIR / "ai_batches"
AI_RESULTS_DIR = DATA_DIR / "ai_results"
CARDS_DIR = DATA_DIR / "cards"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://news:senha@localhost:5432/news_radar",
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AI_BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    AI_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def load_feeds_config(path: Path = FEEDS_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de feeds não encontrado: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("feeds", [])
    return data
