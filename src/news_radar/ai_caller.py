from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import OLLAMA_MODEL, OLLAMA_URL, AI_RESULTS_DIR
from .ai_batches import get_ai_batch, import_ai_result, _update_batch_status


def call_ollama(prompt: str, model: str = OLLAMA_MODEL, timeout: int = 300) -> str:
    response = requests.post(
        f"{OLLAMA_URL.rstrip('/')}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("Ollama retornou resposta sem choices.")
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise ValueError("Ollama retornou resposta sem content.")
    return str(content).strip()


def send_ai_batch(batch_id: str, model: str = OLLAMA_MODEL, timeout: int = 300) -> dict[str, Any]:
    batch = get_ai_batch(batch_id)
    if not batch:
        raise ValueError(f"Lote nao encontrado: {batch_id}")

    prompt_path = Path(batch["prompt_path"])
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt nao encontrado: {prompt_path}")

    _update_batch_status(batch_id, status="running", model=model, error=None, started=True)

    try:
        prompt = prompt_path.read_text(encoding="utf-8")
        raw_content = call_ollama(prompt, model=model, timeout=timeout)

        result_path = AI_RESULTS_DIR / f"{batch_id}.result.json"
        result_path.write_text(raw_content, encoding="utf-8")

        imported = import_ai_result(result_path, batch_id=batch_id)
        return {
            "batch_id": batch_id,
            "status": "completed",
            "model": model,
            "result_file": str(result_path),
            "updated": imported["updated"],
            "ignored": imported["ignored"],
        }
    except Exception as exc:
        _update_batch_status(batch_id, status="failed", model=model, error=str(exc), completed=True)
        raise
