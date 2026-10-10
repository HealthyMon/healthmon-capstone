"""Opt-in character voice; independent of numeric growth and quest policy."""
from __future__ import annotations

import copy
import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "persona_voices.json"


def load_character_voices() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def apply_character_voice(style_profile: dict, character_voice: str = "default") -> dict:
    """Add expression guidance without altering any existing numeric control.

    The default is deliberately a no-op: old evaluation contexts and prompts
    retain their exact representation. Sassy gets a separate metadata field and
    appended guidance, never different personality values, rewards or goals.
    """
    voices = load_character_voices()
    if character_voice not in voices:
        raise ValueError("Unknown character voice")
    if character_voice == "default":
        return style_profile
    voice = voices[character_voice]
    result = copy.deepcopy(style_profile)
    result["character_voice"] = {
        "id": character_voice,
        "label": voice["label"],
        "description": voice["description"],
        "version": voice["version"],
    }
    existing = result.get("guidance", [])
    if isinstance(existing, str):
        existing = [existing]
    result["guidance"] = list(existing) + list(voice["guidance"])
    return result
