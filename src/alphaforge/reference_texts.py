"""Textes de référence fixes (flux B, tâche B7).

Charge les fichiers de `reference/` écrits par l'équipe :
- `limits.json` : limites obligatoires, un texte par niveau (novice, pro) ;
- `fixed_texts.json` : avertissements fixes et phrase sur les seuils.

Ces textes sont affichés par le code, jamais écrits par un modèle. Aucun chiffre
financier n'y figure. Un fichier absent ou invalide est une erreur (`ValueError`),
jamais un texte vide : un avertissement ne doit pas disparaître en silence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
LIMITS_PATH = REFERENCE_DIR / "limits.json"
FIXED_TEXTS_PATH = REFERENCE_DIR / "fixed_texts.json"

LEVELS = ("novice", "pro")

# Sujets obligatoires : biais du survivant, historique de cinq ans, dates et
# devises, hypothèses de simulation, qualité et disponibilité des données.
REQUIRED_LIMIT_TOPICS = (
    "survivorship_bias", "limited_history", "dates_and_currencies",
    "simulation_assumptions", "data_quality_availability",
)
# Avertissements obligatoires : simulation fictive, usage éducatif, absence de
# conseil personnalisé, absence de transactions réelles.
REQUIRED_WARNING_TOPICS = (
    "fictional_simulation", "educational_use", "no_personalized_advice", "no_real_transactions",
)


def _check_level(level: str) -> str:
    if level not in LEVELS:
        raise ValueError(f"Niveau inconnu : {level!r}. Valeurs permises : {', '.join(LEVELS)}.")
    return "text_novice" if level == "novice" else "text_pro"


def _read(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Texte de référence illisible : {path.name} ({error!r})") from error
    if not isinstance(data, dict):
        raise ValueError(f"Texte de référence invalide : {path.name}")
    return data


def _validated_items(items: Any, id_key: str, required_topics: Sequence[str], name: str):
    if not isinstance(items, list) or not items:
        raise ValueError(f"Texte de référence invalide : liste vide ou absente dans {name}")
    seen_ids, topics = set(), set()
    for item in items:
        try:
            item_id, topic = item[id_key], item["topic"]
            texts = [item["text_novice"], item["text_pro"]]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Entrée invalide dans {name} : {error!r}") from error
        if not all(isinstance(t, str) and t.strip() for t in texts):
            raise ValueError(f"Texte vide dans {name} pour {item_id}")
        if item_id in seen_ids:
            raise ValueError(f"Identifiant en double dans {name} : {item_id}")
        seen_ids.add(item_id)
        topics.add(topic)
    missing = [t for t in required_topics if t not in topics]
    if missing:
        raise ValueError(f"Sujet obligatoire absent de {name} : " + ", ".join(missing))
    return items


def load_limits(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Limites obligatoires du catalogue, dans l'ordre du fichier."""
    target = path or LIMITS_PATH
    return _validated_items(_read(target).get("limits"), "limit_id", REQUIRED_LIMIT_TOPICS, target.name)


def mandatory_limits(level: str, path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Limites obligatoires au format du dossier : `{limit_id, text}`."""
    field = _check_level(level)
    return [{"limit_id": item["limit_id"], "text": item[field]} for item in load_limits(path)]


def merge_mandatory_limits(limits: Sequence[Mapping[str, str]], level: str,
                           path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Place les limites obligatoires en tête, suivies des autres limites données.

    Une limite déjà présente avec l'identifiant d'une limite obligatoire doit avoir
    le même texte, sinon `ValueError` : le texte fixe prime, il n'est pas remplacé.
    """
    fixed = mandatory_limits(level, path)
    fixed_text = {item["limit_id"]: item["text"] for item in fixed}
    others = []
    for item in limits:
        limit_id = item["limit_id"]
        if limit_id in fixed_text:
            if item.get("text") != fixed_text[limit_id]:
                raise ValueError(f"Le texte de la limite obligatoire {limit_id} diffère du catalogue.")
            continue
        others.append({"limit_id": limit_id, "text": item["text"]})
    return fixed + others


def load_fixed_texts(path: Optional[Path] = None) -> Dict[str, Any]:
    """Avertissements et phrase sur les seuils, validés."""
    target = path or FIXED_TEXTS_PATH
    data = _read(target)
    _validated_items(data.get("disclaimers"), "warning_id", REQUIRED_WARNING_TOPICS, target.name)
    threshold = data.get("threshold_assumption")
    if not isinstance(threshold, dict) or not all(
            isinstance(threshold.get(k), str) and threshold[k].strip() for k in ("text_novice", "text_pro")):
        raise ValueError(f"Phrase sur les seuils absente ou vide dans {target.name}")
    return data


def disclaimers(level: str, path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Avertissements fixes du niveau : `{warning_id, topic, text}`."""
    field = _check_level(level)
    return [{"warning_id": item["warning_id"], "topic": item["topic"], "text": item[field]}
            for item in load_fixed_texts(path)["disclaimers"]]


def disclaimer_text(level: str, path: Optional[Path] = None) -> str:
    """Les avertissements du niveau en un seul paragraphe."""
    return " ".join(item["text"] for item in disclaimers(level, path))


def threshold_assumption(level: str, path: Optional[Path] = None) -> str:
    """Phrase fixe rappelant que les seuils sont des hypothèses."""
    return load_fixed_texts(path)["threshold_assumption"][_check_level(level)]
