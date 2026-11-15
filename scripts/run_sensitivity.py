"""Mise à l'épreuve des hypothèses : rapport de sensibilité des verdicts (P1-6).

Refait l'évaluation de la gouvernance pour les 3 personas fictifs et les 5 demandes
prêtes de l'interface, en changeant un seul choix à la fois (fenêtre, devise, date
d'arrêt des données, fréquence, seuils), puis sur des blocs annuels disjoints. Écrit :

- `outputs/reports/sensitivity.md` : rapport lisible (faits, hypothèses, synthèse, détail) ;
- `outputs/reports/sensitivity.json` : mêmes résultats, pour vérification.

Sortie déterministe (aucun horodatage) : deux exécutions sur les mêmes données donnent
les mêmes fichiers. Aucun appel AWS, aucune prévision. Simulation éducative sur des
profils et des portefeuilles fictifs.

Usage (depuis la racine) ::

    .venv/Scripts/python scripts/run_sensitivity.py
    .venv/Scripts/python scripts/run_sensitivity.py --out-dir outputs/reports
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge import sensitivity as sens  # noqa: E402
from alphaforge.explanation_rendering import format_percent  # noqa: E402
from alphaforge.portfolio import apply_idea  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs" / "reports"
DETAIL_PERSONA, DETAIL_IDEA = "robert", "TSLA_25"
BLOCK_IDEA = "TSLA_25"
STATUS_SHORT = {"compliant": "conforme", "tension": "tension", "conflict": "conflit",
                "missing_info": "info. manquante", None: "sans objet"}
NON_THRESHOLD_AXES = ("fenetre", "devise", "date_arret", "frequence")

DISCLAIMER = (
    "> **Avertissement.** Simulation éducative sur des profils, portefeuilles et capitaux fictifs. "
    "Ce rapport décrit le passé sous plusieurs conventions ; il ne prédit aucun rendement et "
    "n'est pas un conseil financier personnalisé. Les seuils des règles sont des hypothèses de l'équipe."
)


def _status(code, comparable=True):
    text = STATUS_SHORT.get(code, str(code))
    return text if comparable else f"{text} (non comparable)"


def _pct(value):
    return "sans objet" if value is None else format_percent(value)


def _idea_label(idea_key):
    ticker, weight = idea_key.rsplit("_", 1)
    return f"{ticker} {weight} %"


def _verdict(outcome):
    """Verdict financier comparable, avec renvoi si le verdict brut diffère."""
    text = _status(outcome["financial_comparable"])
    return text if outcome["financial"] == outcome["financial_comparable"] else f"{text} (*)"


def _rule_key_label(key, labels):
    persona, rule_id = key.split(":", 1)
    return f"{persona.capitalize()} {rule_id} {labels.get(key, '')}".strip()


def _factor(value):
    return "sans objet" if value is None else f"{value:.2f}".replace(".", ",")


def build_report(personas: dict) -> tuple[str, dict]:
    """Calcule toute la grille et rend le rapport Markdown et sa version JSON."""
    end = sens.data_end_date()
    rows = sens.run_grid(personas)
    summary = sens.axis_summary(rows)
    variants = {v.variant_id: v for v in sens.GRID_VARIANTS}
    detail = next(r for r in rows if r["persona"] == DETAIL_PERSONA and r["idea"] == DETAIL_IDEA)
    base_detail = detail["outcomes"]["base"]

    detail_profile = personas[DETAIL_PERSONA]["profile"]
    rules_by_id = {rule["rule_id"]: rule for rule in detail_profile["rules"]}
    flips = {rule_id: {"value": info["value"], **sens.flip_factor(rules_by_id[rule_id], info["value"])}
             for rule_id, info in base_detail["rules"].items()}

    blocks = sens.annual_blocks()
    block_rows = {}
    for name in sorted(personas):
        idea = next(i for i in sens.DEFAULT_IDEAS if sens.idea_id(i) == BLOCK_IDEA)
        after = apply_idea(personas[name]["portfolio"], idea, "sensitivity")
        profile = personas[name]["profile"]
        block_base = sens.evaluate_variant(profile, after, "portfolio_after", sens.BASE)
        block_rows[name] = [
            asdict(sens.with_comparable_verdict(block_base, sens.evaluate_variant(profile, after, "portfolio_after", block)))
            for block in blocks]

    stable_rules = sens.stable_rules_by_persona(rows, axes=NON_THRESHOLD_AXES)
    rule_labels = {f"{row['persona']}:{rule_id}": info["label_fr"]
                   for row in rows for rule_id, info in row["outcomes"]["base"]["rules"].items()}

    lines = ["# Mise à l'épreuve des hypothèses", "", DISCLAIMER, ""]
    lines += [
        "## Ce qui est testé",
        "",
        "Les verdicts de la gouvernance reposent sur des choix de l'équipe. Ce rapport refait "
        "l'évaluation en changeant **un seul choix à la fois** et montre quelles règles changent de "
        "statut, pour les 3 personas fictifs et les 5 demandes prêtes de l'interface (financement au "
        "prorata), soit "
        f"{len(rows)} cas par variante. Les verdicts portent sur le portefeuille après l'idée.",
        "",
        "Reproduire : `.venv/Scripts/python scripts/run_sensitivity.py` (aucun appel AWS, sortie identique "
        "à chaque exécution).",
        "",
        "## Faits",
        "",
        f"- Données : `data/raw/prices_daily.csv` (prix ajustés `adj_close`) et `data/raw/fx_usdcad_daily.csv` "
        f"(taux USD/CAD de la Banque du Canada), calendrier commun aux marchés, arrêtées au {end}.",
        f"- Cas de base : du {base_detail['period_start']} au {base_detail['period_end']}, "
        f"{base_detail['n_observations']} rendements quotidiens en CAD, portefeuille rééquilibré chaque jour.",
        "- Chaque valeur du rapport est recalculée par le code (`src/alphaforge/sensitivity.py`) avec les "
        "mêmes fonctions que les outils des agents ; le cas de base redonne exactement leurs chiffres.",
        "",
        "## Hypothèses testées",
        "",
        "| Variante | Ce qui change | Hypothèse |",
        "| --- | --- | --- |",
    ]
    lines += [f"| `{v.variant_id}` | {v.label_fr} | {v.hypothesis_fr} |" for v in sens.GRID_VARIANTS]
    lines += [
        "",
        "Une perte maximale mesurée sur une période plus courte (fenêtre, bloc, date d'arrêt plus ancienne) "
        "ou sur des points hebdomadaires ne peut que baisser ou rester égale : son statut est marqué « non "
        "comparable », n'est pas compté comme un changement, et garde son statut du cas de base dans le "
        "verdict financier comparé. Un verdict suivi de (*) aurait été différent en comptant cette règle.",
        "",
        "## Synthèse par variante",
        "",
        "Les variantes ne sont ni indépendantes ni équiprobables : ce décompte n'est pas une probabilité.",
        "",
        "| Variante | Cas dont le verdict financier change | Règles qui changent de statut, par persona (nombre de cas) |",
        "| --- | --- | --- |",
    ]
    for item in summary:
        changes = "<br>".join(f"{c['persona'].capitalize()}, {_idea_label(c['idea'])} : {_status(c['before'])} "
                              f"devient {_status(c['after'])}" for c in item["financial_verdict_changes"]) or "aucun"
        rule_changes = ", ".join(f"{_rule_key_label(key, rule_labels)} ({count})"
                                 for key, count in item["rule_changes"].items()) or "aucune"
        lines.append(f"| {item['label_fr']} | {len(item['financial_verdict_changes'])} sur {item['n_cases']} : "
                     f"{changes} | {rule_changes} |")
    lines += [
        "",
        "Règles dont le statut ne change avec aucune variante de fenêtre, devise, date d'arrêt ou fréquence "
        "(les identifiants sont propres à chaque persona) : "
        + " ; ".join(f"{persona.capitalize()} : {', '.join(ids) or 'aucune'}" for persona, ids in stable_rules.items())
        + ". Ce sont des règles sur les poids du portefeuille (concentration, part défensive, classes d'actifs, "
        "exclusions, préférence ESG), qui ne dépendent pas des prix.",
        "",
        "## Grille des verdicts financiers",
        "",
        "Verdict financier après l'idée (les règles ESG sont à part : sans source ESG documentée, la règle "
        "d'exclusion ESG de Mateo reste en « information manquante » dans toutes les variantes).",
        "",
        "| Persona | Idée | " + " | ".join(f"`{v}`" for v in variants) + " |",
        "| --- | --- | " + " | ".join("---" for _ in variants) + " |",
    ]
    for row in rows:
        label = _idea_label(row["idea"]) + (" (sans effet)" if row["no_effect"] else "")
        cells = [_verdict(row["outcomes"][v]) for v in variants]
        lines.append(f"| {row['persona'].capitalize()} | {label} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "« Sans effet » : le poids visé est déjà le poids actuel du titre dans le portefeuille fictif.",
        "",
        f"## Détail : {DETAIL_PERSONA.capitalize()}, {_idea_label(DETAIL_IDEA)}",
        "",
        "| Variante | Période | Rendements | Volatilité annualisée | Perte maximale | R1 Concentration | "
        "R2 Volatilité | R3 Perte maximale | Verdict financier |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for variant_id, outcome in detail["outcomes"].items():
        rules = outcome["rules"]
        lines.append(
            f"| {variants[variant_id].label_fr} | {outcome['period_start']} au {outcome['period_end']} | "
            f"{outcome['n_observations']} | {_pct(outcome['volatility_ann'])} | {_pct(outcome['max_drawdown'])} | "
            + " | ".join(_status(rules[r]["status"], rules[r]["comparable"]) for r in ("R1", "R2", "R3"))
            + f" | {_verdict(outcome)} |")
    lines += [
        "",
        "### Jusqu'où les seuils peuvent bouger",
        "",
        "Facteur d'échelle des seuils auquel le statut d'une règle change (cas de base), dans le même sens "
        "que les variantes de seuils : en dessous de 1, seuils plus stricts (plafond abaissé, plancher "
        "relevé) ; au-dessus de 1, plus souples. Exemple : un facteur de 1,25 sur le seuil d'attention veut "
        "dire qu'avec un facteur de 1,25 ou plus (seuils plus souples), la valeur mesurée ne le franchit plus ; "
        "un facteur de 0,82 veut dire qu'avec un facteur de 0,82 ou moins (seuils plus stricts), elle le franchit.",
        "",
        "| Règle | Valeur mesurée | Seuil d'attention | Facteur (attention) | Limite | Facteur (limite) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rule_id, flip in flips.items():
        rule = rules_by_id[rule_id]
        if rule.get("rule_type") in sens.NON_SCALABLE_RULE_TYPES:
            continue
        lines.append(f"| {rule_id} {rule['label_fr']} | {_pct(flip['value'])} | {_pct(rule.get('warn_threshold'))} | "
                     f"{_factor(flip['warn'])} | {_pct(rule.get('limit_threshold'))} | {_factor(flip['limit'])} |")
    lines += [
        "",
        f"## Blocs annuels disjoints : {_idea_label(BLOCK_IDEA)}",
        "",
        "Chaque bloc est une seule année observée. Ces épisodes décrivent le passé (dont la baisse de 2022), "
        "ils ne prévoient rien. La perte maximale d'une année n'est pas comparable aux seuils fixés pour 5 ans. "
        "La date de début d'un bloc est sa date de base (dernier prix du bloc précédent) : les rendements de "
        "deux blocs ne se recouvrent pas.",
        "",
    ]
    for name, outcomes in block_rows.items():
        lines += [f"**{name.capitalize()}**", "",
                  "| Bloc | Rendements | Volatilité annualisée | Perte maximale (non comparable) | R2 Volatilité | "
                  "Verdict financier |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for outcome in outcomes:
            lines.append(f"| Du {outcome['period_start']} au {outcome['period_end']} | {outcome['n_observations']} | {_pct(outcome['volatility_ann'])} | "
                         f"{_pct(outcome['max_drawdown'])} | {_status(outcome['rules']['R2']['status'])} | "
                         f"{_verdict(outcome)} |")
        lines.append("")
    lines += [
        "## Limites",
        "",
        "- Un seul choix change à la fois : les effets combinés ne sont pas testés.",
        "- Les variantes de période réutilisent l'univers et les portefeuilles choisis en 2026 (biais de "
        "survie) : se placer en 2024 ne reproduit pas ce qu'on savait en 2024.",
        "- Une fenêtre d'un an compte environ 250 rendements : indicatif seulement.",
        "- La devise locale suppose un change parfaitement couvert, sans coût : c'est une convention de "
        "calcul, pas une stratégie disponible.",
        "- La volatilité et la perte maximale décrivent le passé ; elles sont un indicateur de risque parmi "
        "d'autres (horizon, diversification, préférences).",
        "- La composition (poids, classes, secteurs) ne change pas d'une variante à l'autre : seuls les "
        "risques mesurés sur les prix et le groupe corrélé sont recalculés.",
        "",
    ]
    payload = {
        "data_end": end,
        "variants": [asdict(v) for v in sens.GRID_VARIANTS],
        "grid": rows,
        "summary": summary,
        "detail": {"persona": DETAIL_PERSONA, "idea": DETAIL_IDEA, "flip_factors": flips},
        "annual_blocks": {"idea": BLOCK_IDEA, "blocks": [asdict(b) for b in blocks], "results": block_rows},
        "stable_rules_non_threshold_axes": stable_rules,
    }
    return "\n".join(lines), payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport de sensibilité des verdicts (simulation éducative).")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="Dossier de sortie (défaut : outputs/reports)")
    args = parser.parse_args(argv)
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    markdown, payload = build_report(load_personas())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sensitivity.md").write_text(markdown, encoding="utf-8")
    (out_dir / "sensitivity.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                                              encoding="utf-8")
    print(f"Rapport écrit : {out_dir / 'sensitivity.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
