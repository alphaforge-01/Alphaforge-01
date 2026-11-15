"""Libellés français des classes d'actifs, secteurs et devises de l'univers.

Pourquoi : `assets_universe.csv` (données des organisateurs, en lecture seule) nomme les
classes d'actifs par des codes (`equity`, `etf_bond`) et les secteurs en anglais
(`Consumer Discretionary`). Ces noms se retrouvaient tels quels dans les libellés des
preuves, donc à l'écran, dans le dossier de l'explicateur et dans la source du contrôle
d'ancrage. Ce module donne le libellé français ; les clés de preuve (`evidence_key`)
gardent le code d'origine, qui reste la référence stable.

Mêmes traductions que `app/ui_texts.py` (ASSET_CLASS_LABELS, SECTOR_LABELS), pour que
l'interface et les preuves disent la même chose. Un nom inconnu est rendu tel quel.
"""
from __future__ import annotations

ASSET_CLASS_FR = {
    "equity": "Actions",
    "etf_equity": "FNB d'actions",
    "etf_bond": "FNB d'obligations",
    "etf_commodity": "FNB de matières premières",
    "crypto": "Cryptoactifs",
}

SECTOR_FR = {
    "Financials": "Finance",
    "Energy": "Énergie",
    "Industrials": "Industrie",
    "Utilities": "Services publics",
    "Consumer Staples": "Consommation de base",
    "Consumer Discretionary": "Consommation discrétionnaire",
    "Information Technology": "Technologies de l'information",
    "Communication Services": "Services de communication",
    "Health Care": "Santé",
    "Broad market (Canada)": "Marché large (Canada)",
    "Broad market (U.S.)": "Marché large (États-Unis)",
    "Broad market (U.S. growth/tech-heavy)": "Marché large (États-Unis, croissance et technologie)",
    "Broad market (U.S., ESG-screened)": "Marché large (États-Unis, filtre ESG)",
    "Bonds (Canada aggregate)": "Obligations (Canada, ensemble du marché)",
    "Bonds (Canada ultra short-term)": "Obligations (Canada, très court terme)",
    "Bonds (U.S. aggregate)": "Obligations (États-Unis, ensemble du marché)",
    "Bonds (U.S. long Treasury)": "Obligations (Trésor américain, long terme)",
    "Gold": "Or",
    "Crypto asset": "Cryptoactif",
}

CURRENCY_FR = {
    "CAD": "dollar canadien (CAD)",
    "USD": "dollar américain (USD)",
}


def asset_class_fr(name: str) -> str:
    """Libellé français d'une classe d'actifs (code d'origine si inconnu)."""
    return ASSET_CLASS_FR.get(name, name)


def sector_fr(name: str) -> str:
    """Libellé français d'un secteur (nom d'origine si inconnu)."""
    return SECTOR_FR.get(name, name)


def currency_fr(code: str) -> str:
    """Libellé français d'une devise (code d'origine si inconnu)."""
    return CURRENCY_FR.get(code, code)
