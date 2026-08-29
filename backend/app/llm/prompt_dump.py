"""Opt-in prompt capture for demos and debugging.

Normal operation never logs prompt or response text (see openai_provider).
When ``LLM_DEBUG_DUMP_PROMPTS`` is on, every prompt actually sent to the model
is written verbatim to ``logs/prompts/`` so you can show, for example, that a
retrieved study-material excerpt really made it into the LLM input.

Never enable this outside a local demo / dev environment: the files contain the
full prompt, including student text and uploaded material.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

log = logging.getLogger("app.llm.prompt_dump")

_DIR = Path(__file__).resolve().parents[2] / "logs" / "prompts"


def dump(operation: str, system: str, user: str) -> None:
    """Write one prompt to a timestamped file. No-op unless the flag is set."""
    if not settings.LLM_DEBUG_DUMP_PROMPTS:
        return
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        path = _DIR / f"{stamp}_{operation}.txt"
        marker = "STUDY MATERIAL THE STUDENT UPLOADED"
        has_material = marker in system or marker in user
        path.write_text(
            f"operation: {operation}\n"
            f"captured_at: {stamp} UTC\n"
            f"study_material_in_prompt: {has_material}\n"
            f"\n===== SYSTEM =====\n{system}\n"
            f"\n===== USER =====\n{user}\n",
            encoding="utf-8",
        )
        log.info(
            "prompt dumped op=%s file=%s study_material_in_prompt=%s",
            operation,
            path.name,
            has_material,
        )
    except Exception:  # noqa: BLE001 - a debug aid must never break a turn
        log.warning("prompt dump failed op=%s", operation, exc_info=True)
