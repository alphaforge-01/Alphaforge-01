"""Mesure de la compréhension des messages de la page Simulation (jeu de 60 phrases étiquetées).

Écrit `outputs/reports/dialogue_eval.md` et `dialogue_eval.json` : taux de réussite global et par
catégorie, et la liste des phrases ratées avec ce que le système a compris. Sortie déterministe.

Aujourd'hui, le compreneur mesuré est celui des règles déterministes (`request_parsing`). Un
interprète sur Bedrock pourra être mesuré avec le même jeu en lui passant la même signature
(voir `alphaforge.dialogue_eval.evaluate`). Aucun appel AWS ici. Phrases inventées, portefeuille
fictif de Robert.

Usage (depuis la racine) ::

    .venv/Scripts/python scripts/measure_dialogue.py
    .venv/Scripts/python scripts/measure_dialogue.py --out-dir outputs/reports
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge import dialogue_eval  # noqa: E402
from alphaforge.data_loading import load_universe  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs" / "reports"
SAFETY_CATEGORIES = ("refus", "idee_explicite", "piege")


def _fmt(observed: dict) -> str:
    parts = [f"{key} {value}" for key, value in observed.items() if value not in (None, ())]
    return ", ".join(parts) or "rien"


def render(report: dict, phrases: dict, label: str) -> str:
    lines = [
        "# Compréhension des messages : mesure sur 60 phrases",
        "",
        "> Simulation éducative : phrases inventées, portefeuille fictif de Robert. Aucun appel AWS.",
        "",
        f"Compreneur mesuré : **{label}**. Chaque phrase porte le comportement idéal attendu "
        "(jamais deviner un actif ou un poids, refuser ce qui est interdit), défini dans "
        "`tests/fixtures/dialogue_phrases.json`. Une phrase réussit si chaque champ attendu "
        "(statut, intention, terme, actif, poids, raison) correspond.",
        "",
        f"**Résultat : {report['ok']} phrases sur {report['total']}.**",
        "",
        "| Catégorie | Réussies | Ce qui est testé |",
        "| --- | --- | --- |",
    ]
    for category, description in phrases["categories"].items():
        stats = report["by_category"].get(category, {"ok": 0, "total": 0})
        mark = " (sécurité)" if category in SAFETY_CATEGORIES else ""
        lines.append(f"| {category}{mark} | {stats['ok']}/{stats['total']} | {description} |")
    missed = [row for row in report["rows"] if not row["ok"]]
    lines += ["", "## Phrases ratées", ""]
    if not missed:
        lines.append("Aucune.")
    else:
        lines += ["| Id | Phrase | Attendu | Compris |", "| --- | --- | --- | --- |"]
        for row in missed:
            text = row["text"].replace("|", "/")
            lines.append(f"| {row['id']} | {text} | {_fmt(row['expected'])} | {_fmt(row['observed'])} |")
    lines += [
        "",
        "## Lecture",
        "",
        "- Les catégories de sécurité (refus, idées explicites, pièges) doivent rester à 100 % : "
        "un test le vérifie à chaque modification.",
        "- Les autres phrases ratées donnent la liste de ce qu'un interprète (compréhension par un "
        "modèle) ou un agent conversationnel devra couvrir, sans jamais deviner.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mesure de la compréhension des messages (sans AWS).")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Dossier de sortie")
    args = parser.parse_args(argv)
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    phrases = dialogue_eval.load_phrases()
    persona = load_personas()[phrases["persona"]]
    held = [position["ticker"] for position in persona["portfolio"]["positions"]]
    report = dialogue_eval.evaluate(dialogue_eval.rules_understand, load_universe().to_dict("records"),
                                    held, phrases)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dialogue_eval.md").write_text(render(report, phrases, "règles déterministes (lot 1)"),
                                              encoding="utf-8")
    (out_dir / "dialogue_eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(f"Compréhension : {report['ok']} phrases sur {report['total']}. Rapport : {out_dir / 'dialogue_eval.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
