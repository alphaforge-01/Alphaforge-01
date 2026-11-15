"""Jeu de scénarios fixes : 3 personas x 5 demandes fictives (les boutons de l'interface), à relire avant la démo (flux A, tâche A7).

Fait tourner le pipeline complet (`analysis_pipeline.run_analysis` puis `explain`
aux niveaux novice et pro) sur un jeu de demandes fixe, et écrit dans
`outputs/reports/scenarios/<mode>_<horodatage>/` :

- `summary.md` : verdicts avant et après, règles non conformes, contrefactuels,
  variantes, origine et validité des explications, taux de rejet du validateur ;
- `results.json` : les mêmes informations en JSON (aucun secret, aucune trace brute) ;
- `explanations/<persona>__<scénario>__<niveau>.md` : le texte rendu, pour relecture humaine.

Usage (depuis la racine du projet) :

    .venv/Scripts/python scripts/run_scenarios.py                       # hors ligne, sans AWS
    .venv/Scripts/python scripts/run_scenarios.py --mode bedrock        # agents réels
    .venv/Scripts/python scripts/run_scenarios.py --mode bedrock --persona robert

Mode `bedrock` : appels réels aux modèles avec les identifiants temporaires de
l'environnement (jamais écrits ni affichés). Pour 3 personas, jusqu'à 12 boucles
de l'analyste, environ 48 appels Converse et 24 contrôles du garde-fou, plus une
trace S3 par appel si `ALPHAFORGE_TRACE_BUCKET` est défini : quotas partagés de
l'équipe, à lancer seulement pour régler les prompts ou avant la démo (utiliser
`--persona` pour réduire). Si la configuration est incomplète, le pipeline
retombe en mode hors ligne : le rapport l'indique et le script rend le code 2.

Les rapports générés sont ignorés par git (`outputs/reports/scenarios/`) : ne
versionner qu'une exécution relue, copiée sous un nom fixe.

Les demandes sont des scénarios fictifs de démonstration : simulation éducative,
pas un conseil personnalisé, aucune recommandation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alphaforge.bedrock_client import redact_text  # noqa: E402
from alphaforge.governance import split_verdicts  # noqa: E402
from alphaforge.profiles import load_personas  # noqa: E402

DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs" / "reports" / "scenarios"
LEVELS = ("novice", "pro")
LARGEST_HOLDING = "<largest>"  # remplacé par la plus grosse position du persona
DOUBLE_REJECTION = "rejet_du_validateur"
EXPLAINER_FAILURE_PREFIXES = ("ExplainerFailure", "AgentFailure", "BedrockError",
                              "explicateur_indisponible", "configuration_incomplete")
EXIT_OK, EXIT_FAILURES, EXIT_NO_LLM = 0, 1, 2


@dataclass(frozen=True)
class Scenario:
    """Une demande fictive appliquée à chaque persona (`target_weight` = poids total visé)."""

    scenario_id: str
    label_fr: str
    idea: dict


# Les 5 demandes prêtes de l'interface (`app/ui_texts.py`, IDEA_PRESETS), financement au prorata :
# le rapport montre exactement ce qu'un utilisateur obtient en cliquant sur un bouton.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario("tsla_25",
             "Demande fictive : porter TSLA à 25 % du portefeuille, financement au prorata (titre très médiatisé)",
             {"ticker": "TSLA", "target_weight": 0.25, "funding_source": "pro_rata", "funding_ticker": None}),
    Scenario("nvda_15",
             "Demande fictive : porter NVDA à 15 %, financement au prorata (technologie émergente)",
             {"ticker": "NVDA", "target_weight": 0.15, "funding_source": "pro_rata", "funding_ticker": None}),
    Scenario("btc_10",
             "Demande fictive : porter BTC-USD à 10 %, financement au prorata (cryptoactif, petite part)",
             {"ticker": "BTC-USD", "target_weight": 0.10, "funding_source": "pro_rata", "funding_ticker": None}),
    Scenario("btc_40",
             "Demande fictive : porter BTC-USD à 40 %, financement au prorata (cryptoactif, grosse part)",
             {"ticker": "BTC-USD", "target_weight": 0.40, "funding_source": "pro_rata", "funding_ticker": None}),
    Scenario("xom_15",
             "Demande fictive : porter XOM à 15 %, financement au prorata (énergie, préférences ESG)",
             {"ticker": "XOM", "target_weight": 0.15, "funding_source": "pro_rata", "funding_ticker": None}),
)


@dataclass
class ScenarioOutcome:
    """Résultat d'un couple persona et demande (types simples, sérialisable en JSON)."""

    persona: str
    scenario_id: str
    idea: dict
    ok: bool
    no_effect: bool = False
    error: str | None = None
    is_fixture: bool | None = None
    effective_mode: str | None = None
    analyst_actor: str | None = None
    analyst_fallback_reason: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    financial_after: str | None = None   # verdict des seules règles financières (P1-9)
    esg_after: str | None = None         # verdict des règles ESG, None si le profil n'en a pas
    non_compliant: list = field(default_factory=list)
    counterfactuals: dict = field(default_factory=dict)
    variants: list = field(default_factory=list)
    explanations: dict = field(default_factory=dict)
    duration_ms: int = 0


def resolve_idea(idea: dict, portfolio: dict) -> dict:
    """Remplace `LARGEST_HOLDING` par la plus grosse position du portefeuille fictif."""
    if idea.get("funding_ticker") != LARGEST_HOLDING:
        return dict(idea)
    positions = sorted(portfolio["positions"], key=lambda p: (-p["weight"], p["ticker"]))
    candidates = [p["ticker"] for p in positions if p["ticker"] != idea["ticker"]]
    return {**idea, "funding_ticker": candidates[0] if candidates else None}


def has_no_effect(idea: dict, portfolio: dict) -> bool:
    """Vrai si le portefeuille détient déjà exactement le poids visé (demande sans effet)."""
    current = {p["ticker"]: p["weight"] for p in portfolio["positions"]}.get(idea["ticker"], 0.0)
    return abs(current - idea["target_weight"]) < 1e-9


def _trace_step(trace: list, name: str) -> dict:
    return next((step for step in trace or [] if step.get("name") == name), {})


def _is_explainer_failure(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(EXPLAINER_FAILURE_PREFIXES)


def _summarize_explanation(explanation: dict) -> dict:
    """Résumé d'une explication.

    L'étape 4 de la trace décrit le texte du modèle même quand le gabarit l'a
    ensuite remplacé : `details.origin` et `details.attempt` sont ceux du modèle.
    """
    output = explanation.get("output") or {}
    validation = explanation.get("validation") or {}
    guardrail = explanation.get("guardrail") or {}
    details = _trace_step(explanation.get("trace"), "explanation").get("details") or {}
    llm_produced = details.get("origin") == "llm"
    llm_attempt = details.get("attempt") or 1
    llm_rejection_codes = sorted(set(details.get("rejection_codes") or []))
    fallback_reason = details.get("fallback_reason")
    return {
        "displayed_origin": output.get("origin"),
        "llm_produced": llm_produced,
        "llm_attempt": llm_attempt if llm_produced else None,
        "first_attempt_not_kept": llm_produced and (llm_attempt > 1 or bool(llm_rejection_codes)),
        "rejected_twice": llm_produced and fallback_reason == DOUBLE_REJECTION,
        "explainer_failed": _is_explainer_failure(fallback_reason),
        "llm_rejection_codes": llm_rejection_codes,
        "final_rejection_codes": sorted({r.get("code") for r in validation.get("rejections") or []}),
        "is_valid": validation.get("is_valid"),
        "fallback_reason": fallback_reason,
        "guardrail_action": guardrail.get("action"),
        "grounding_score": guardrail.get("grounding_score"),
        "rendered_markdown": explanation.get("rendered_markdown") or "",
    }


def run_one(persona: str, data: dict, scenario: Scenario, mode: str, as_of: str | None,
            run_analysis: Callable, explain: Callable, levels=LEVELS) -> ScenarioOutcome:
    """Fait tourner un scénario ; une erreur est consignée, jamais propagée."""
    idea = resolve_idea(scenario.idea, data["portfolio"])
    outcome = ScenarioOutcome(persona=persona, scenario_id=scenario.scenario_id, idea=idea, ok=False,
                              no_effect=has_no_effect(idea, data["portfolio"]))
    start = time.perf_counter()
    try:
        result = run_analysis(data["profile"], data["portfolio"], idea, as_of=as_of, mode=mode)
        outcome.is_fixture = bool(result.get("is_fixture"))
        outcome.effective_mode = result.get("mode")
        analysis_step = _trace_step(result.get("trace"), "analysis")
        outcome.analyst_actor = analysis_step.get("actor")
        outcome.analyst_fallback_reason = (analysis_step.get("details") or {}).get("fallback_reason")
        outcome.status_before = result["governance_before"]["overall_status"]
        outcome.status_after = result["governance_after"]["overall_status"]
        verdicts = split_verdicts(result["governance_after"])
        outcome.financial_after, outcome.esg_after = verdicts["financial"], verdicts["esg"]
        checks = result["governance_after"]["checks"]
        outcome.non_compliant = [f"{c['rule_id']} {c['label_fr']} : {c['status']}"
                                 for c in checks if c["status"] != "compliant"]
        outcome.counterfactuals = {c["rule_id"]: (c.get("counterfactual") or {}).get("display_value")
                                   for c in checks if c.get("counterfactual")}
        outcome.variants = [{"variant_id": v["variant_id"], "reason_code": v["reason_code"],
                             "target_weight": v["idea"]["target_weight"],
                             "funding_ticker": v["idea"].get("funding_ticker"),
                             "status": v["governance"]["overall_status"]} for v in result.get("variants") or []]
        for level in levels:
            outcome.explanations[level] = _summarize_explanation(explain(result, level, mode=mode))
        outcome.ok = True
    except Exception as error:  # le script consigne et continue : un scénario ne bloque pas les autres
        traceback.print_exc(file=sys.stderr)  # console seulement, jamais dans les fichiers
        outcome.error = f"{type(error).__name__} : {redact_text(str(error))[:300]}"
    outcome.duration_ms = int((time.perf_counter() - start) * 1000)
    return outcome


def rejection_rate(outcomes: list[ScenarioOutcome]) -> tuple[int, int]:
    """(textes du modèle dont le premier essai n'a pas été retenu, textes produits par le modèle).

    Le dénominateur compte les textes réellement rédigés par le modèle, y compris
    ceux remplacés ensuite par le gabarit ; il exclut les échecs de l'explicateur
    (aucun texte produit).
    """
    produced = [e for o in outcomes for e in o.explanations.values() if e.get("llm_produced")]
    return sum(1 for e in produced if e["first_attempt_not_kept"]), len(produced)


def llm_used(outcomes: list[ScenarioOutcome]) -> bool:
    return any(e.get("llm_produced") for o in outcomes for e in o.explanations.values())


def render_summary(outcomes: list[ScenarioOutcome], mode: str, as_of: str | None, generated_at: str) -> str:
    """Rapport Markdown en français."""
    not_kept, produced = rejection_rate(outcomes)
    explanations = [e for o in outcomes for e in o.explanations.values()]
    rejected_twice = sum(1 for e in explanations if e.get("rejected_twice"))
    explainer_failed = sum(1 for e in explanations if e.get("explainer_failed"))
    invalid = sum(1 for e in explanations if e.get("is_valid") is False)
    failures = [o for o in outcomes if not o.ok]
    fixtures = sum(1 for o in outcomes if o.is_fixture)
    effective = sorted({o.effective_mode for o in outcomes if o.effective_mode})
    no_effect = [o for o in outcomes if o.no_effect]
    lines = [
        "# Jeu de scénarios fixes",
        "",
        f"Généré le {generated_at}. Mode demandé : `{mode}` ; mode effectif : "
        f"{', '.join(f'`{m}`' for m in effective) or 'inconnu'}. Date d'analyse : {as_of or 'fin des données'}.",
        "",
        "Simulation éducative, pas un conseil personnalisé : demandes et portefeuilles fictifs, "
        "aucune recommandation. Les verdicts viennent de la gouvernance en code.",
        "",
        "## Indicateurs",
        "",
        f"- Scénarios : {len(outcomes)} ({len(failures)} en échec, {len(no_effect)} sans effet).",
        f"- Résultats sur données d'essai (bouchons) : {fixtures}.",
        f"- Explications invalides après repli : {invalid}.",
    ]
    if produced:
        lines += [
            f"- Premier essai non retenu (rejet du validateur ou JSON invalide) : {not_kept} sur {produced} "
            "textes rédigés par le modèle.",
            f"- Rejeté deux fois, gabarit affiché : {rejected_twice}.",
            f"- Échecs de l'explicateur (aucun texte produit, hors taux) : {explainer_failed}.",
        ]
    else:
        lines.append("- Taux de rejet du validateur : sans objet (aucun texte rédigé par un modèle dans ce mode).")
    if mode == "bedrock" and not produced:
        lines.append("- **Attention : mode bedrock demandé, mais aucun texte n'a été rédigé par le modèle "
                     "(repli hors ligne ou explicateur indisponible).**")
    lines += [
        "",
        "## Scénarios",
        "",
        "| Persona | Demande | Avant | Après | Financier / ESG après | Règles non conformes | Contrefactuels | "
        "Variantes | Explications (novice / pro) | Durée |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    labels = {s.scenario_id: s.label_fr for s in SCENARIOS}
    for o in outcomes:
        label = labels.get(o.scenario_id, o.scenario_id) + (" **(sans effet)**" if o.no_effect else "")
        if not o.ok:
            lines.append(f"| {o.persona} | {label} | échec | échec | | {o.error} | | | | {o.duration_ms} ms |")
            continue
        texts = " / ".join(
            ("modèle" if e["llm_produced"] else "gabarit")
            + (f" puis gabarit ({e['fallback_reason']})" if e["llm_produced"] and e["displayed_origin"] == "template" else "")
            + (f", essai {e['llm_attempt']}" if e["llm_produced"] else "")
            + (", valide" if e["is_valid"] else ", invalide")
            + (f", codes du modèle : {', '.join(e['llm_rejection_codes'])}" if e["llm_rejection_codes"] else "")
            for e in o.explanations.values())
        variants = "; ".join(f"{v['variant_id']} {v['reason_code']} {v['target_weight']:.0%} : {v['status']}"
                             for v in o.variants) or "aucune"
        counterfactuals = "; ".join(f"{k} : {v}" for k, v in o.counterfactuals.items()) or "aucun"
        lines.append(
            f"| {o.persona} | {label} | {o.status_before} | **{o.status_after}** | "
            f"{o.financial_after or 'aucune règle financière'} / {o.esg_after or 'aucune règle ESG'} | "
            f"{'<br>'.join(o.non_compliant) or 'aucune'} | {counterfactuals} | {variants} | {texts} | {o.duration_ms} ms |")
    lines += [
        "",
        "## À relire",
        "",
        "- Les textes complets sont dans `explanations/`. Vérifier le ton, l'absence de recommandation et de prévision, "
        "et que chaque chiffre renvoie à une preuve.",
        "- Signaler tout verdict surprenant (par exemple un profil prudent conforme avec une demande spéculative).",
        "- Préférences ESG : tant que les preuves ESG (A9, P2) n'existent pas, un contrôle ESG doit rendre "
        "`missing_info` ; un verdict `compliant` sans contrôle ESG ne prouve rien sur l'ESG.",
        "- Le premier essai non retenu peut venir d'un rejet du validateur ou d'un JSON illisible : les deux ne sont "
        "pas distingués aujourd'hui.",
    ]
    return "\n".join(lines) + "\n"


def write_report(outcomes: list[ScenarioOutcome], out_dir: Path, mode: str, as_of: str | None,
                 now: datetime | None = None) -> Path:
    """Écrit summary.md, results.json et les textes ; rend le dossier du rapport."""
    now = now or datetime.now()
    run_dir = out_dir / f"{mode}_{now.strftime('%Y%m%d_%H%M%S')}"
    (run_dir / "explanations").mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.md").write_text(
        render_summary(outcomes, mode, as_of, now.strftime("%Y-%m-%d %H:%M")), encoding="utf-8")
    payload = []
    for o in outcomes:
        record = {k: v for k, v in o.__dict__.items() if k != "explanations"}
        record["explanations"] = {level: {k: v for k, v in e.items() if k != "rendered_markdown"}
                                  for level, e in o.explanations.items()}
        payload.append(record)
        for level, e in o.explanations.items():
            name = f"{o.persona}__{o.scenario_id}__{level}.md"
            (run_dir / "explanations" / name).write_text(e["rendered_markdown"], encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def run_all(mode: str = "offline", as_of: str | None = None, personas: list[str] | None = None,
            run_analysis: Callable | None = None, explain: Callable | None = None) -> list[ScenarioOutcome]:
    """Tous les scénarios pour les personas demandés (tous par défaut)."""
    if run_analysis is None or explain is None:
        from alphaforge import analysis_pipeline

        run_analysis = run_analysis or analysis_pipeline.run_analysis
        explain = explain or analysis_pipeline.explain
    data = load_personas()
    selected = personas or sorted(data)
    unknown = sorted(set(selected) - set(data))
    if unknown:
        raise SystemExit(f"Personas inconnus : {unknown}")
    return [run_one(name, data[name], scenario, mode, as_of, run_analysis, explain)
            for name in selected for scenario in SCENARIOS]


def resolve_out_dir(out: Path) -> Path:
    """Un chemin relatif est rattaché à la racine du projet, jamais au dossier courant."""
    return out if out.is_absolute() else PROJECT_ROOT / out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jeu de scénarios fixes (3 personas x 5 demandes fictives, les boutons de l'interface).")
    parser.add_argument("--mode", choices=("offline", "bedrock"), default="offline",
                        help="offline : sans AWS (par défaut) ; bedrock : agents réels, quotas partagés.")
    parser.add_argument("--as-of", default=None, help="Date d'analyse AAAA-MM-JJ (par défaut : fin des données).")
    parser.add_argument("--persona", action="append", dest="personas", help="Limiter à un persona (répétable).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Dossier de sortie.")
    args = parser.parse_args(argv)

    if args.mode == "bedrock":
        print("Mode bedrock : appels réels aux modèles, quotas partagés de l'équipe.")
    outcomes = run_all(args.mode, args.as_of, args.personas)
    run_dir = write_report(outcomes, resolve_out_dir(args.out), args.mode, args.as_of)
    not_kept, produced = rejection_rate(outcomes)
    failures = sum(1 for o in outcomes if not o.ok)
    print(f"{len(outcomes)} scénarios, {failures} en échec. Premier essai non retenu : {not_kept}/{produced}.")
    for o in outcomes:
        status = f"{o.status_before} -> {o.status_after}" if o.ok else f"ÉCHEC ({o.error})"
        print(f"  {o.persona:8} {o.scenario_id:22} {status}{' (sans effet)' if o.no_effect else ''}")
    shown = run_dir.relative_to(PROJECT_ROOT) if run_dir.is_relative_to(PROJECT_ROOT) else run_dir
    print(f"Rapport : {shown}")
    if failures:
        return EXIT_FAILURES
    if args.mode == "bedrock" and not llm_used(outcomes):
        print("Attention : aucun texte rédigé par le modèle (repli hors ligne ou explicateur indisponible).")
        return EXIT_NO_LLM
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
