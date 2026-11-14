"""Cache des explications generees par l'explicateur.

Cle : (identifiant du dossier, niveau, modele, version du prompt). Le contenu du
dossier etant resume dans ``brief_id``, un changement de preuves, de regles ou de
limites produit une nouvelle cle. Memoire seulement par defaut ; un fichier JSON
facultatif (sous ``data/processed/``, ignore par Git) permet de survivre a un
redemarrage. Aucun secret n'est stocke : seulement des textes d'explication.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CacheKey = tuple[str, str, str, str]


class ExplanationCache:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._items: dict[str, dict[str, Any]] = {}
        if path is not None and path.is_file():
            try:
                self._items = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._items = {}

    @staticmethod
    def make_key(brief_id: str, level: str, model_id: str, prompt_version: str) -> str:
        return "|".join((brief_id, level, model_id, prompt_version))

    def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        return json.loads(json.dumps(item)) if item is not None else None

    def put(self, key: str, output: dict[str, Any]) -> None:
        self._items[key] = json.loads(json.dumps(output))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._items, ensure_ascii=False), encoding="utf-8")

    def __len__(self) -> int:
        return len(self._items)


DEFAULT_CACHE = ExplanationCache()
