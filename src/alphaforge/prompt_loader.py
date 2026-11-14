"""Chargement des prompts systeme versionnes depuis ``prompts/``."""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> str:
    """Lit ``prompts/<name>.md``. Le nom du fichier sert de version (``analyst_v1``)."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt introuvable : {name}")
    return path.read_text(encoding="utf-8")
