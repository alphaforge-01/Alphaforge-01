"""Bouchons temporaires bases sur les fixtures de ``tests/fixtures/``.

Ils permettent au pipeline du flux C de tourner de bout en bout en mode
``offline`` tant que les flux A (outils) et B (gouvernance, explication) ne
sont pas fusionnes. Les chiffres sont INVENTES : tout resultat produit avec
ces bouchons porte ``is_fixture=True`` et l'interface affiche le bandeau
"donnees d'essai". Ce module disparait de l'usage des qu'``alphaforge.agent_tools``
et les modules du flux B existent (voir ``pipeline_deps.resolve_deps``).

Perimetre volontairement etroit : profils robert et amira, idee TSLA a 25 %.
Pas de variantes (``supports_variants=False``), la fixture n'en contient aucune.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .pipeline_deps import PipelineDeps

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
SUPPORTED_PROFILES = ("robert", "amira")
_STATUS_ORDER = {"conflict": 0, "tension": 1, "missing_info": 2, "compliant": 3}
_STATUS_LABEL_FR = {
    "conflict": "en conflit", "tension": "en tension",
    "missing_info": "information manquante", "compliant": "conforme",
}
_REF = re.compile(r"\[([A-Z]\d+)\]")


def _load(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _world(profile_id: str) -> dict[str, Any]:
    if profile_id not in SUPPORTED_PROFILES:
        raise ValueError(f"Pas de fixture pour le profil {profile_id}.")
    return _load(f"analysis_result_{profile_id}_tsla.json")


def _analyze_portfolio(portfolio: dict, as_of: str | None = None, capital_cad: float | None = None) -> dict:
    world = _world("robert")
    evidence = [e for e in world["evidence"].values() if e["subject"] == "portfolio_before"]
    return {
        "tool_name": "analyze_portfolio", "call_id": "fixture-call", "params": {"portfolio_id": portfolio["portfolio_id"]},
        "status": "ok", "error_message": None, "data": copy.deepcopy(world["snapshot_before"]),
        "evidence": copy.deepcopy(evidence),
    }


def _get_asset_facts(ticker: str, as_of: str | None = None) -> dict:
    return {
        "tool_name": "get_asset_facts", "call_id": "fixture-call", "params": {"ticker": ticker},
        "status": "ok", "error_message": None, "data": {"ticker": ticker, "note": "bouchon"}, "evidence": [],
    }


def _simulate_portfolio_change(portfolio: dict, idea: dict, as_of: str | None = None, capital_cad: float | None = None) -> dict:
    world = _world("robert")
    evidence = [e for e in world["evidence"].values() if e["subject"] != "portfolio_before"]
    return {
        "tool_name": "simulate_portfolio_change", "call_id": "fixture-call", "params": dict(idea),
        "status": "ok", "error_message": None,
        "data": {"before": copy.deepcopy(world["snapshot_before"]), "after": copy.deepcopy(world["snapshot_after"])},
        "evidence": copy.deepcopy(evidence),
    }


class _IdentityRegistry:
    """Les preuves des fixtures portent deja leurs identifiants."""

    @staticmethod
    def register(tool_result: dict) -> dict:
        return tool_result


def _evaluate(profile: dict, snapshot: dict, simulate_fn: Any = None, idea: dict | None = None) -> dict:
    world = _world(profile["profile_id"])
    key = "governance_before" if snapshot.get("subject") == "portfolio_before" else "governance_after"
    governance = copy.deepcopy(world[key])
    governance["subject"] = snapshot.get("subject", governance.get("subject"))
    return governance


def _ranked_factors(checks: list[dict]) -> list[dict]:
    ordered = sorted(checks, key=lambda c: (_STATUS_ORDER[c["status"]], c["margin"] if c["margin"] is not None else 0))
    return [
        {"rank": i + 1, "check_id": c["check_id"], "status": c["status"], "evidence_ids": c["evidence_ids"]}
        for i, c in enumerate(ordered)
    ]


def _build_brief(result: dict, level: str) -> dict:
    brief = _load("explanation_brief_robert_novice.json")
    checks = copy.deepcopy(result["governance_after"]["checks"])
    brief.update({
        "brief_id": f"fixture-brief-{result['profile']['profile_id']}-{level}",
        "run_id": result["run_id"], "level": level, "idea": result["idea"],
        "profile_rules": result["profile"]["rules"], "checks": checks,
        "ranked_factors": _ranked_factors(checks),
        "evidence": list(result["evidence"].values()),
    })
    key = "text_pro" if level == "pro" else "text_novice"
    brief["limits"] = [{"limit_id": l["limit_id"], "text": l[key]} for l in result["limits"]]
    return brief


def _render_template(brief: dict) -> dict:
    factors = brief["ranked_factors"]
    first = factors[0] if factors else None
    summary = (
        f"La regle [{first['check_id']}] est {{status}} selon [{first['evidence_ids'][0]}]."
        if first and first["evidence_ids"] else "Aucune regle a signaler."
    )
    if first:
        summary = summary.replace("{status}", _STATUS_LABEL_FR[first["status"]])
    return {
        "brief_id": brief["brief_id"], "level": brief["level"], "summary": summary,
        "factors": [
            {"check_id": f["check_id"], "text": f"La regle [{f['check_id']}] est {_STATUS_LABEL_FR[f['status']]}."}
            for f in factors
        ],
        "counterfactual": "Voir le seuil de la regle [" + (first["check_id"] if first else "G1") + "].",
        "variants": "Aucune variante simulee en mode bouchon.",
        "limits_context": " ".join(l["text"] for l in brief["limits"]),
        "origin": "template", "model_id": None, "prompt_version": None, "attempt": 0,
    }


def _validate(output: dict, brief: dict) -> dict:
    known = {e["evidence_id"] for e in brief["evidence"]} | {c["check_id"] for c in brief["checks"]} \
        | {g["term_id"] for g in brief.get("glossary", [])}
    texts = [output["summary"], output["counterfactual"], output["variants"], output["limits_context"]]
    texts += [f["text"] for f in output["factors"]]
    rejections: list[dict] = []
    checked: list[str] = []
    for slot_text in texts:
        for ref in _REF.findall(slot_text):
            checked.append(ref)
            if ref not in known:
                rejections.append({"code": "unknown_reference", "slot": "text", "excerpt": ref})
        if re.search(r"\d", _REF.sub("", slot_text)):
            rejections.append({"code": "number_outside_registry", "slot": "text", "excerpt": slot_text[:40]})
    return {"is_valid": not rejections, "rejections": rejections, "checked_references": checked}


def _render_markdown(output: dict, brief: dict) -> str:
    evidence = {e["evidence_id"]: e["display_value"] for e in brief["evidence"]}
    checks = {c["check_id"]: c["label_fr"] for c in brief["checks"]}

    def sub(text: str) -> str:
        return _REF.sub(lambda m: evidence.get(m.group(1), checks.get(m.group(1), m.group(0))), text)

    lines = [sub(output["summary"]), ""]
    lines += [f"- {sub(f['text'])}" for f in output["factors"]]
    lines += ["", sub(output["counterfactual"]), "", sub(output["variants"]), "", sub(output["limits_context"])]
    return "\n".join(lines)


def _limits_for(limit_ids: list[str]) -> list[dict]:
    wanted = set(limit_ids)
    return [limit for limit in _world("robert")["limits"] if not wanted or limit["limit_id"] in wanted]


def fixture_deps() -> PipelineDeps:
    return PipelineDeps(
        analyze_portfolio=_analyze_portfolio,
        get_asset_facts=_get_asset_facts,
        simulate_portfolio_change=_simulate_portfolio_change,
        make_registry=_IdentityRegistry,
        evaluate=_evaluate,
        build_brief=_build_brief,
        render_template=_render_template,
        validate=_validate,
        render_markdown=_render_markdown,
        is_fixture=True,
        supports_variants=False,
        limits_for=_limits_for,
    )
