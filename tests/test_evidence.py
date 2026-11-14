"""Tests du registre de preuves (alphaforge.evidence)."""
import copy

import pytest

from alphaforge import evidence
from alphaforge.evidence import EvidenceError, EvidenceRegistry, make_entry
from alphaforge.explanation_rendering import format_percent


def _entry(metric="volatility_ann", subject="portfolio_after", value=0.2):
    return make_entry(tool_name="t", metric=metric, subject=subject, value=value,
                      display_value="x", as_of="2024-01-02", limit_ids=["LM1"])


def _result(call_id, metrics=("volatility_ann", "max_drawdown")):
    return {"tool_name": "t", "call_id": call_id, "params": {}, "status": "ok",
            "error_message": None, "data": {}, "evidence": [_entry(metric=m) for m in metrics]}


# --- Registre ---

def test_numerotation_sequentielle_par_instance():
    registry = EvidenceRegistry()
    registry.register(_result("a"))
    registry.register(_result("b"))
    assert list(registry.entries) == ["E1", "E2", "E3", "E4"], "Numerotation E1.. sequentielle attendue"
    other = EvidenceRegistry()
    assert list(other.entries) == [], "Une nouvelle instance repart de zero"
    result = other.register(_result("c"))
    assert result["evidence"][0]["evidence_id"] == "E1", "Chaque instance numerote depuis E1"


def test_register_rend_le_meme_objet_et_modifie_sur_place():
    registry = EvidenceRegistry()
    result = _result("a")
    first_entry = result["evidence"][0]
    returned = registry.register(result)
    assert returned is result, "Le meme ToolResult doit etre rendu"
    assert result["evidence"][0] is first_entry
    assert first_entry["evidence_id"] == "E1", "L'entree doit etre modifiee sur place"
    assert registry.get("E1") is first_entry


def test_idempotence_meme_resultat():
    registry = EvidenceRegistry()
    result = _result("a")
    registry.register(result)
    ids = [e["evidence_id"] for e in result["evidence"]]
    registry.register(result)
    assert [e["evidence_id"] for e in result["evidence"]] == ids
    assert len(registry) == 2, "Pas de doublon apres un deuxieme enregistrement"


def test_idempotence_copie_profonde_meme_call_id():
    registry = EvidenceRegistry()
    result = _result("a")
    registry.register(result)
    clone = copy.deepcopy(result)
    for entry in clone["evidence"]:
        entry["evidence_id"] = "Z9"
    registry.register(clone)
    assert [e["evidence_id"] for e in clone["evidence"]] == ["E1", "E2"]
    assert len(registry) == 2


def test_pas_de_fusion_par_evidence_key():
    registry = EvidenceRegistry()
    one, two = _result("a", ("volatility_ann",)), _result("b", ("volatility_ann",))
    assert one["evidence"][0]["evidence_key"] == two["evidence"][0]["evidence_key"]
    registry.register(one)
    registry.register(two)
    assert one["evidence"][0]["evidence_id"] != two["evidence"][0]["evidence_id"]
    assert len(registry) == 2


@pytest.mark.parametrize("status", ["error", "missing_info"])
def test_statut_non_ok_laisse_intact(status):
    registry = EvidenceRegistry()
    result = _result("a")
    result["status"] = status
    result["evidence"][0]["evidence_id"] = "KEEP"
    registry.register(result)
    assert result["evidence"][0]["evidence_id"] == "KEEP", "Un resultat non ok n'est pas touche"
    assert len(registry) == 0


def test_identifiants_entrants_ecrases():
    registry = EvidenceRegistry()
    result = _result("a")
    result["evidence"][0]["evidence_id"] = "E99"
    registry.register(result)
    assert result["evidence"][0]["evidence_id"] == "E1"


def test_entries_get_find_len():
    registry = EvidenceRegistry()
    result = registry.register(_result("a"))
    assert len(registry) == 2
    assert registry.get("E3") is None
    assert registry.find("max_drawdown", "portfolio_after") == [result["evidence"][1]]
    assert registry.find("max_drawdown", "autre") == []
    registry.entries.clear()
    assert len(registry) == 2, "entries rend une copie du dictionnaire"


# --- make_entry ---

def test_make_entry_rejets():
    base = dict(tool_name="t", subject="s", value=1, display_value="x", as_of="2024-01-02", limit_ids=["LM1"])
    with pytest.raises(EvidenceError):
        make_entry(metric="volatility_ann", unit="eur", **base)
    with pytest.raises(EvidenceError):
        make_entry(metric="volatility_ann", **{**base, "limit_ids": ["L1"]})
    with pytest.raises(EvidenceError):
        make_entry(metric="inconnue", **base)
    with pytest.raises(EvidenceError):
        make_entry(metric="volatility_ann", **{**base, "value": None})
    with pytest.raises(EvidenceError):
        make_entry(metric="volatility_ann:x", **base)


def test_make_entry_famille_composee_et_cle():
    entry = make_entry(tool_name="t", metric="weight_by_sector.Information Technology", subject="variant:V1",
                       value=0.1, display_value="10 %", as_of="2024-01-02", limit_ids=[])
    assert entry["evidence_key"] == "weight_by_sector.Information Technology:variant:V1"
    assert entry["unit"] == "pct"
    assert entry["evidence_id"] == ""
    assert evidence.evidence_key("max_drawdown", "TSLA") == "max_drawdown:TSLA"
    with pytest.raises(EvidenceError):
        evidence.evidence_key("a:b", "s")


# --- Formats ---

@pytest.mark.parametrize("days,expected", [(1, "1 jour"), (412, "412 jours"), (1234, "1 234 jours")])
def test_format_days(days, expected):
    assert evidence.format_days(days) == expected


@pytest.mark.parametrize("amount,expected", [(26040, "26 040 $"), (0, "0 $")])
def test_format_cad(amount, expected):
    assert evidence.format_cad(amount) == expected


@pytest.mark.parametrize("delta,expected", [(0.016, "+1,6 pts"), (-0.0875, "-8,75 pts"), (0.0, "0 pts")])
def test_format_signed_points(delta, expected):
    assert evidence.format_signed_points(delta) == expected


@pytest.mark.parametrize("value", [0.0, 0.4125, 0.25, -0.2604])
def test_percent_display_egale_format_percent(value):
    assert evidence.percent_display(value) == format_percent(value)


def test_limites_connues_egales_au_catalogue():
    """Les identifiants de limites acceptés viennent du catalogue du flux B."""
    from alphaforge.evidence import KNOWN_LIMIT_IDS
    from alphaforge.reference_texts import load_limits

    assert set(KNOWN_LIMIT_IDS) == {item["limit_id"] for item in load_limits()}


def test_make_entry_refuse_une_valeur_non_finie():
    """NaN ou infini : refusé, comme None."""
    import pytest

    from alphaforge.evidence import EvidenceError, make_entry

    with pytest.raises(EvidenceError):
        make_entry(tool_name="t", metric="volatility_ann", subject="s", value=float("nan"),
                   display_value="?", as_of="2024-01-01", limit_ids=["LM1"])
