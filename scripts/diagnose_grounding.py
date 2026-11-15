"""Diagnostic de l'ancrage de l'explication : pourquoi le score du garde-fou reste bas.

Le contrôle d'ancrage de Bedrock Guardrails compare le texte de l'explication à une
source. Ce script compare deux sources pour le même texte :
- "json" : le dossier d'explication en JSON, ce que le pipeline envoie aujourd'hui ;
- "phrases" : le même dossier réécrit en phrases françaises
  (src/alphaforge/grounding_source.py), sans aucun fait ajouté.

Texte contrôlé : les emplacements de l'explication, renvois remplacés par les valeurs
affichées, exactement comme dans le pipeline (`_model_text`). Par défaut, ce texte vient
du gabarit du code, fidèle par construction : son score est le plafond atteignable avec
une source donnée. Si même le gabarit est mal ancré, la cause est la source, pas le modèle.

Modes :
- par défaut : hors ligne, aucun appel réseau. Mesures lexicales : part des mots, des
  statuts et des chiffres du texte que l'on retrouve tels quels dans chaque source ;
- ``--apply`` : appelle réellement ``ApplyGuardrail`` (quota partagé), pour chaque cas et
  chaque source : sur le texte du gabarit, puis sur un témoin négatif (le même texte avec
  toutes les règles déclarées conformes), soit au plus 4 appels par cas. Le témoin vérifie
  qu'une source plus lisible ne rend pas le contrôle indulgent.
  Exige ALPHAFORGE_GUARDRAIL_ID et ALPHAFORGE_GUARDRAIL_VERSION ;
- ``--explainer`` (avec ``--apply``) : fait aussi rédiger le texte par l'agent explicateur
  sur Bedrock (au plus 2 appels Converse par cas), pour mesurer le vrai texte du modèle.
  Exige aussi ALPHAFORGE_EXPLAINER_MODEL_ID.

Budget : au plus 6 cas (3 personas x 2 niveaux, idée fixe "25 % dans TSLA au prorata").
Aucun texte de prompt, de dossier ni aucun secret n'est affiché : seulement des scores et
des compteurs. Simulation éducative sur des profils et portefeuilles fictifs.

Usage, depuis la racine du projet (pour --apply : dans le terminal qui contient les
identifiants temporaires, après ``aws sts get-caller-identity``) ::

    python scripts/diagnose_grounding.py
    python scripts/diagnose_grounding.py --apply
    python scripts/diagnose_grounding.py --apply --explainer --personas robert

Codes de sortie : 0 succès, 2 configuration ou budget.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge.analysis_pipeline import _model_text, run_analysis  # noqa: E402
from alphaforge.bedrock_client import (  # noqa: E402
    GROUNDING_ANSWER_MAX_CHARS, GROUNDING_SOURCE_MAX_CHARS, BedrockClient, BedrockConfig, redact_text,
)
from alphaforge.grounding_source import build_grounding_source  # noqa: E402
from alphaforge.pipeline_deps import resolve_deps  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
MAX_CASES = 6
# Même requête fixe que l'étape 6 du pipeline (analysis_pipeline.explain).
QUERY = "Explique le resultat de l'analyse."
IDEA = {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}
LEVELS = ("novice", "pro")
STATUS_WORDS = ("conflit", "tension", "conforme", "information manquante")
NUMBER_PATTERN = re.compile(r"[-+]?\d[\d ]*(?:,\d+)? ?(?:%|pts|\$|jours)")
WORD_PATTERN = re.compile(r"[a-z]{5,}")


def fold(text: str) -> str:
    """Minuscules sans accents, pour comparer des mots."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def lexical_report(checked: str, source: str) -> Dict[str, Any]:
    """Part du texte retrouvée telle quelle dans la source : indicateur grossier, pas un score d'ancrage."""
    checked_folded, source_folded = fold(checked), fold(source)
    words = set(WORD_PATTERN.findall(checked_folded))
    source_words = set(WORD_PATTERN.findall(source_folded))
    missing_words = sorted(words - source_words)
    statuses = [word for word in STATUS_WORDS if word in checked_folded]
    numbers = sorted(set(NUMBER_PATTERN.findall(checked)))
    return {
        "source_chars": len(source),
        "words_found": f"{len(words) - len(missing_words)}/{len(words)}",
        "statuses_missing": [word for word in statuses if word not in source_folded],
        "numbers_missing": [number for number in numbers if number not in source],
        "examples_missing": missing_words[:12],
    }


def build_cases(persona_ids: List[str]) -> List[Dict[str, Any]]:
    """Analyse hors ligne (outils et gouvernance réels, aucun agent), puis dossier par niveau."""
    deps = resolve_deps()
    personas = load_personas()
    cases = []
    for persona_id in persona_ids:
        persona = personas[persona_id]
        result = run_analysis(persona["profile"], persona["portfolio"], IDEA, mode="offline")
        for level in LEVELS:
            brief = deps.build_brief(result, level)
            cases.append({"persona": persona_id, "level": level, "brief": brief,
                          "template": deps.render_template(brief), "validate": deps.validate})
    return cases


def falsify(text: str) -> str:
    """Témoin négatif : le même texte, mais toutes les règles déclarées conformes.

    Une source plus lisible ne doit pas rendre le contrôle indulgent : le score de ce
    texte faux doit rester nettement sous celui du texte juste.
    """
    for wrong in ("en conflit", "en tension", "conflit", "tension"):
        text = text.replace(wrong, "conforme")
    return text


def grounding_scores(client: BedrockClient, source: str, checked: str) -> str:
    if len(source) > GROUNDING_SOURCE_MAX_CHARS or len(checked) > GROUNDING_ANSWER_MAX_CHARS:
        return "trop long"
    result = client.check_output_grounding(source, QUERY, checked)
    if result["action"] == "not_run":
        return "non exécuté"
    grounding, relevance = result["grounding_score"], result["relevance_score"]
    return (f"ancrage {'-' if grounding is None else f'{grounding:.2f}'}, "
            f"pertinence {'-' if relevance is None else f'{relevance:.2f}'}")


def llm_text(client: BedrockClient, config: BedrockConfig, case: Dict[str, Any]) -> Optional[str]:
    """Texte de l'agent explicateur, s'il passe le validateur ; sinon None."""
    from alphaforge.explainer_agent import explain_with_llm
    try:
        output = explain_with_llm(client, config.explainer_model_id, case["brief"], case["validate"])
    except Exception as error:  # un échec du modèle est un résultat du diagnostic, pas une panne
        print(f"    explicateur indisponible : {type(error).__name__}: {redact_text(str(error))}")
        return None
    if not case["validate"](output, case["brief"])["is_valid"]:
        print("    texte de l'explicateur rejeté par le validateur : cas ignoré")
        return None
    return _model_text(output, case["brief"])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--personas", default="robert,amira,mateo",
                        help="personas fictifs, séparés par des virgules (défaut : les trois)")
    parser.add_argument("--apply", action="store_true", help="appelle réellement ApplyGuardrail")
    parser.add_argument("--explainer", action="store_true",
                        help="avec --apply, fait aussi rédiger le texte par l'explicateur Bedrock")
    args = parser.parse_args(argv)

    persona_ids = [name.strip() for name in args.personas.split(",") if name.strip()]
    if len(persona_ids) * len(LEVELS) > MAX_CASES:
        print(f"Budget dépassé : au plus {MAX_CASES} cas.")
        return EXIT_CONFIG_ERROR
    if args.explainer and not args.apply:
        print("--explainer exige --apply.")
        return EXIT_CONFIG_ERROR
    config = client = None
    if args.apply:
        config = BedrockConfig.from_env()
        if not config.has_guardrail:
            print("Garde-fou non configuré : définir ALPHAFORGE_GUARDRAIL_ID et ALPHAFORGE_GUARDRAIL_VERSION.")
            return EXIT_CONFIG_ERROR
        if args.explainer and not config.explainer_model_id:
            print("Explicateur non configuré : définir ALPHAFORGE_EXPLAINER_MODEL_ID.")
            return EXIT_CONFIG_ERROR
        client = BedrockClient(config)

    for case in build_cases(persona_ids):
        sources = {"json": json.dumps(case["brief"], ensure_ascii=False),
                   "phrases": build_grounding_source(case["brief"])}
        template_text = _model_text(case["template"], case["brief"])
        texts = {"gabarit": template_text}
        if client is not None and falsify(template_text) != template_text:
            texts["gabarit faussé (témoin)"] = falsify(template_text)
        print(f"\n== {case['persona']} | niveau {case['level']} ==")
        if args.explainer:
            generated = llm_text(client, config, case)
            if generated:
                texts["explicateur"] = generated
        for text_name, checked in texts.items():
            print(f"  texte {text_name} ({len(checked)} caractères)")
            for source_name, source in sources.items():
                report = lexical_report(checked, source)
                line = (f"    source {source_name:<8} {report['source_chars']:>6} car. | mots retrouvés "
                        f"{report['words_found']:>6} | statuts absents {report['statuses_missing'] or '-'} | "
                        f"chiffres absents {report['numbers_missing'] or '-'}")
                if client is not None:
                    line += " | " + grounding_scores(client, source, checked)
                print(line)
                if report["examples_missing"]:
                    print(f"      mots absents (extrait) : {', '.join(report['examples_missing'])}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
