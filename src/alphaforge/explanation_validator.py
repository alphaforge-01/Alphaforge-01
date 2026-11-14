"""Validateur d'explication (flux B, tâche B6).

`validate(output, brief)` contrôle un `ExplainerOutput` (gabarit ou modèle) contre
le `ExplanationBrief` dont il est issu. Il rend un `ValidationResult` :
`{is_valid, rejections: [{code, slot, excerpt}], checked_references}`.

Codes de rejet (fixés par `contracts.py`) :
- `unknown_reference` : renvoi `[E..]`, `[G..]` ou `[T..]` absent du dossier, renvoi
  mal formé (`[E1, E2]`, `[X1]`, `[e1]`) ou identifiant écrit sans crochets (`G1`) ;
  facteur dont le `check_id` est inconnu du dossier ;
- `number_outside_registry` : chiffre absent des preuves du dossier, ou nombre écrit
  en lettres ("trois", "un quart", "le double"). Les nombres en lettres sont toujours
  rejetés, car aucun registre ne permet de les vérifier ;
- `forbidden_term` : recommandation, ordre d'achat ou de vente, prévision, promesse,
  jugement flatteur ("rassurant", "solide") ;
- `missing_rule_citation` : contrôle en tension, en conflit ou en information
  manquante dont le renvoi `[G..]` n'apparaît nulle part ;
- `slot_missing` : champ obligatoire absent ou vide, facteur manquant ou dans un
  autre ordre que `ranked_factors` ;
- `too_long` : texte plus long que `max_chars_per_slot`.

Limites connues :
- Le validateur ne juge pas le sens des phrases sans chiffre ni renvoi.
- Un nombre qui figure dans le registre est accepté, même appliqué à la mauvaise
  mesure. `allow_registry_numbers=False` impose zéro chiffre en clair, comme le gabarit.
- `brief_id` et `level` de la sortie ne sont pas comparés à ceux du dossier :
  l'appelant garantit la correspondance (clé de cache).
- L'ordre des facteurs n'a pas de code dédié : il est signalé en `slot_missing`.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from alphaforge.contracts import ExplainerOutput, ExplanationBrief, ValidationResult, check_keys

TEXT_SLOTS = ("summary", "counterfactual", "variants", "limits_context")
DEFAULT_MAX_CHARS = 400
NEEDS_CITATION = ("tension", "conflict", "missing_info")
EXCERPT_CONTEXT = 12
EXCERPT_MAX = 80

# Tout groupe entre crochets qui contient un chiffre est un renvoi (valide ou non).
_BRACKET = re.compile(r"\[[^\[\]]*\d[^\[\]]*\]")
_VALID_REF = re.compile(r"\[([EGT]\d+)\]")
_BARE_REF = re.compile(r"(?<![\w\[])[EGT]\d+(?![\w\]])")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"(?<!\d)\d+(?:[ \u00a0\u202f]\d{3}(?!\d))*(?:[.,]\d+)?")

# Nombres et quantités écrits en lettres. "un" et "une" seuls sont des articles : non listés.
_NUMBER_WORDS = (
    r"z[ée]ro|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|"
    r"vingts?|trente|quarante|cinquante|soixante|septante|huitante|octante|nonante|cents?|mille|milles|"
    r"millions?|milliards?|quart|quarts|tiers|moiti[ée]s?|demis?|demie|double|doubles|triple|triples|"
    r"quadruple|dizaines?|douzaines?|centaines?|milliers?"
)
_NUMBER_WORD = re.compile(r"(?<![\w-])(?:" + _NUMBER_WORDS + r")(?![\w])", re.IGNORECASE)

# Termes interdits (comparaison sans accents ni casse). Chaque motif commence à une frontière de mot.
_FORBIDDEN_PATTERNS = (
    # recommandations, ordres, injonctions
    r"recommand\w*", r"conseill\w*", r"sugg[eè]r\w*", r"devriez", r"devrions", r"vous devez",
    r"il faut", r"il faudrait", r"il vaut mieux", r"mieux vaut", r"ach[eè]t\w*", r"vend(?:re|ez|ons|s)",
    r"investissez", r"profitez", r"optez", r"misez", r"renforcez", r"r[ée]duisez", r"augmentez",
    r"[ée]vitez", r"gardez", r"conservez", r"privil[ée]gi\w*", r"saisissez",
    # garanties, certitudes
    r"garanti\w*", r"sans risque", r"[àa] coup s[ûu]r", r"certainement", r"assur[ée]ment", r"sans aucun doute",
    # prévisions, prédictions
    r"pr[ée]vi\w*", r"pr[ée]voi\w*", r"pr[ée]di\w*", r"pronostic\w*", r"s'attendre",
    r"rendements? (?:futurs?|attendus?|esp[ée]r[ée]s?)", r"futurs? rendements?",
    r"va (?:monter|baisser|augmenter|chuter|grimper|progresser|perdre|gagner|rapporter)",
    r"gagnera", r"perdra", r"rapportera", r"augmentera", r"diminuera", r"chutera", r"l'an prochain",
    r"l'ann[ée]e prochaine", r"surperform\w*", r"battra",
    # jugements flatteurs ou alarmistes non fondés sur un seuil
    r"rassurant\w*", r"solides?", r"excellent\w*", r"exceptionnel\w*", r"id[ée]al\w*", r"parfait\w*",
    r"s[ée]curitaires?", r"catastroph\w*",
)
_FORBIDDEN = tuple(re.compile(r"(?<![\w])(?:" + p + r")(?![\w])", re.IGNORECASE) for p in _FORBIDDEN_PATTERNS)

_FOLD_FROM = "éèêëàâäîïôöùûüç’"
_FOLD_TO = "eeeeaaaiioouuuc'"
_FOLD = str.maketrans(_FOLD_FROM, _FOLD_TO)
Rejection = Dict[str, str]


def _fold(text: str) -> str:
    """Minuscules sans accents, même longueur que le texte d'origine (positions conservées)."""
    return text.lower().translate(_FOLD)


def _excerpt(text: str, start: int, end: int) -> str:
    chunk = text[max(0, start - EXCERPT_CONTEXT): end + EXCERPT_CONTEXT]
    chunk = re.sub(r"\s+", " ", chunk).strip()
    return chunk if len(chunk) <= EXCERPT_MAX else chunk[: EXCERPT_MAX - 3] + "..."


def _blank(text: str, spans: Sequence[Tuple[int, int]]) -> str:
    """Remplace des plages par des espaces, sans décaler les positions."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def _canonical(raw: str) -> Optional[str]:
    cleaned = re.sub(r"[ \u00a0\u202f]", "", raw).replace(",", ".")
    try:
        return format(Decimal(cleaned).normalize(), "f")
    except InvalidOperation:
        return None


def _numbers_in(text: str) -> List[str]:
    return [c for c in (_canonical(m.group(0)) for m in _NUMBER.finditer(text)) if c is not None]


def _registry_numbers(brief: Mapping[str, Any]) -> Tuple[Set[str], Set[str]]:
    """Nombres et dates ISO présents dans les preuves du dossier."""
    numbers: Set[str] = set()
    dates: Set[str] = set()
    for entry in brief.get("evidence") or []:
        numbers.update(_numbers_in(str(entry.get("display_value") or "")))
        value = entry.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numbers.add(_canonical(repr(round(float(value), 10))) or "")
            if entry.get("unit") == "pct":
                numbers.add(_canonical(repr(round(float(value) * 100, 8))) or "")
        count = entry.get("n_observations")
        if isinstance(count, int) and not isinstance(count, bool):
            numbers.add(str(count))
        for key in ("period_start", "period_end", "as_of"):
            if isinstance(entry.get(key), str) and _ISO_DATE.fullmatch(entry[key]):
                dates.add(entry[key])
    numbers.discard("")
    return numbers, dates


def _known_ids(brief: Mapping[str, Any]) -> Set[str]:
    ids = {e["evidence_id"] for e in brief.get("evidence") or [] if "evidence_id" in e}
    ids |= {c["check_id"] for c in brief.get("checks") or [] if "check_id" in c}
    ids |= {g["term_id"] for g in brief.get("glossary") or [] if "term_id" in g}
    return ids


def _reject(rejections: List[Rejection], code: str, slot: str, excerpt: str) -> None:
    item = {"code": code, "slot": slot, "excerpt": excerpt}
    if item not in rejections:
        rejections.append(item)


def _check_text(slot: str, text: str, known: Set[str],
                numbers: Set[str], dates: Set[str], allow_registry_numbers: bool,
                max_chars: int, rejections: List[Rejection], checked: List[str],
                cited: Set[str]) -> None:
    if len(text) > max_chars:
        _reject(rejections, "too_long", slot, f"{len(text)} caractères pour {max_chars} permis : "
                + _excerpt(text, 0, 0)[:40])

    # Renvois : valides, inconnus, mal formés.
    spans = []
    for match in _BRACKET.finditer(text):
        spans.append((match.start(), match.end()))
        valid = _VALID_REF.fullmatch(match.group(0))
        if valid and valid.group(1) in known:
            ref = valid.group(1)
            if ref not in checked:
                checked.append(ref)
            cited.add(ref)
        else:
            _reject(rejections, "unknown_reference", slot, match.group(0))
    bare = _blank(text, spans)
    for match in _BARE_REF.finditer(bare):
        _reject(rejections, "unknown_reference", slot, _excerpt(text, match.start(), match.end()))
        spans.append((match.start(), match.end()))
    body = _blank(text, spans)

    # Dates ISO du registre : permises. Autres chiffres : à vérifier.
    date_spans = [(m.start(), m.end()) for m in _ISO_DATE.finditer(body) if m.group(0) in dates]
    body_numbers = _blank(body, date_spans)
    for match in _NUMBER.finditer(body_numbers):
        canonical = _canonical(match.group(0))
        if not allow_registry_numbers or canonical not in numbers:
            _reject(rejections, "number_outside_registry", slot, _excerpt(text, match.start(), match.end()))
    for match in _NUMBER_WORD.finditer(body):
        _reject(rejections, "number_outside_registry", slot, _excerpt(text, match.start(), match.end()))

    # Termes interdits.
    folded = _fold(body)
    for pattern in _FORBIDDEN:
        for match in pattern.finditer(folded):
            _reject(rejections, "forbidden_term", slot, _excerpt(text, match.start(), match.end()))


def _factor_slots(output: Mapping[str, Any], brief: Mapping[str, Any], known: Set[str],
                  rejections: List[Rejection]) -> List[Tuple[str, str]]:
    """Vérifie la structure des facteurs et retourne les `(slot, texte)` à contrôler."""
    factors = output.get("factors")
    if not isinstance(factors, list):
        _reject(rejections, "slot_missing", "factors", "liste de facteurs absente")
        return []
    expected = [f["check_id"] for f in brief.get("ranked_factors") or []]
    checks = {c["check_id"] for c in brief.get("checks") or []}
    slots: List[Tuple[str, str]] = []
    actual: List[str] = []
    for index, factor in enumerate(factors):
        slot = f"factors[{index}]"
        if not isinstance(factor, Mapping) or not isinstance(factor.get("check_id"), str):
            _reject(rejections, "slot_missing", slot, "check_id absent")
            continue
        check_id = factor["check_id"]
        actual.append(check_id)
        if check_id not in checks:
            _reject(rejections, "unknown_reference", slot, check_id)
        text = factor.get("text")
        if not isinstance(text, str) or not text.strip():
            _reject(rejections, "slot_missing", slot, f"texte absent pour {check_id}")
        else:
            slots.append((slot, text))
    for check_id in expected:
        if check_id not in actual:
            _reject(rejections, "slot_missing", "factors", f"facteur manquant : {check_id}")
    known_actual = [c for c in actual if c in checks]
    if all(c in actual for c in expected) and known_actual != expected:
        _reject(rejections, "slot_missing", "factors",
                "ordre ou contenu différent de ranked_factors : attendu " + ", ".join(expected))
    return slots


def validate(output: ExplainerOutput, brief: ExplanationBrief,
             allow_registry_numbers: bool = True) -> ValidationResult:
    """Valide une explication contre son dossier. Ne lève pas d'exception sur une sortie défectueuse.

    `allow_registry_numbers=False` : aucun chiffre en clair n'est permis (mode du gabarit).
    """
    rejections: List[Rejection] = []
    checked: List[str] = []

    if not isinstance(output, Mapping):
        _reject(rejections, "slot_missing", "output", "sortie absente ou non structurée")
        return {"is_valid": False, "rejections": rejections, "checked_references": checked}

    for key in check_keys(output, ExplainerOutput):
        _reject(rejections, "slot_missing", key, "champ obligatoire absent")

    known = _known_ids(brief)
    numbers, dates = _registry_numbers(brief)
    max_chars = brief.get("max_chars_per_slot") or DEFAULT_MAX_CHARS
    cited: Set[str] = set()

    slots: List[Tuple[str, str]] = []
    for name in TEXT_SLOTS:
        if name not in output:
            continue                                   # déjà signalé par check_keys
        text = output[name]
        if not isinstance(text, str) or not text.strip():
            _reject(rejections, "slot_missing", name, "texte absent ou vide")
        else:
            slots.append((name, text))
    if "factors" in output:
        slots.extend(_factor_slots(output, brief, known, rejections))

    for slot, text in slots:
        _check_text(slot, text, known, numbers, dates, allow_registry_numbers, max_chars,
                    rejections, checked, cited)

    for check in brief.get("checks") or []:
        if check.get("status") in NEEDS_CITATION and check["check_id"] not in cited:
            _reject(rejections, "missing_rule_citation", "output",
                    f"[{check['check_id']}] {check.get('label_fr', '')} ({check['status']})".strip())

    return {"is_valid": not rejections, "rejections": rejections, "checked_references": checked}
