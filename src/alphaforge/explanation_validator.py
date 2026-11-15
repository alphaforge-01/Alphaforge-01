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
  jugement flatteur ("rassurant", "solide"), et aussi tout contenu actif ou navigable :
  URL, lien ou image Markdown, balise HTML (voir `_UNSAFE_MARKUP`). Aucun code de rejet
  n'est ajouté : le contrat `ValidationResult` reste inchangé ;
- `missing_rule_citation` : contrôle en tension, en conflit ou en information
  manquante dont le renvoi `[G..]` n'apparaît nulle part ;
- `slot_missing` : champ obligatoire absent ou vide, facteur manquant ou dans un
  autre ordre que `ranked_factors` ;
- `too_long` : texte plus long que `max_chars_per_slot`.

Contrefactuel déclaré indisponible (P0-5) : quand le dossier contient un contrefactuel calculé (contrôle en
tension ou en conflit dont `counterfactual` est présent, avec un poids conforme ou "aucun poids testé"), le code
affiche ces poids sous l'emplacement `counterfactual`. Une proposition de cet emplacement qui les déclare
"pas disponibles", "indisponibles", "non calculés", "impossibles à calculer", "absents des preuves" ou
"aucun contrefactuel" est rejetée (`forbidden_term`, emplacement `counterfactual`). Aucun rejet si le
contrefactuel est `None` (simulation indisponible ou peu fiable), ni pour "aucun poids testé n'est conforme",
ni pour une proposition qui ne cite que des contrôles sans contrefactuel calculé.

Protection contre les liens, images et balises (indépendante de celle de `explainer_agent.py`) :
- rejetés : `http://`, `https://`, `www.`, schémas `javascript:`, `data:`, `file:`, `ftp:`,
  `mailto:`, `vbscript:` ; `![` et `](` (image, lien) ; définition de lien `[x]: ...` en début de ligne ;
  balises HTML (`<a ...>`, `</p>`, `<!-- -->`, `<?`) et balises dangereuses même non fermées
  (`<script`, `<img`, `<iframe`...) ;
- permis : renvois `[E1]` `[G1]` `[T1]` (y compris `([E1])` et `[E1]` suivi d'un espace),
  texte ordinaire, et `<` ou `>` sans forme de balise (`5 < 6`, `<5 %`, `a < b`, `x<y`) ;
- le texte est normalisé (NFKC, sans caractères de largeur nulle) avant l'analyse, pour qu'une
  adresse écrite en caractères pleine largeur ou coupée par un caractère invisible ne
  contourne pas la règle ;
- limite connue : `a<b et c>d` (sans espace, avec un `>` plus loin) ressemble à une balise et
  est rejeté. Le rejet entraîne une nouvelle tentative, puis le gabarit.

Limites connues :
- Le validateur ne juge pas le sens des phrases sans chiffre ni renvoi.
- Une date ISO du registre n'autorise que la date complète, pas ses composantes
  (`2021-12-29` n'autorise pas un `12 %` ni un `29`).
- Un nombre qui figure dans le registre est accepté, même appliqué à la mauvaise
  mesure. `allow_registry_numbers=False` impose zéro chiffre en clair, comme le gabarit.
- `brief_id` et `level` de la sortie ne sont pas comparés à ceux du dossier :
  l'appelant garantit la correspondance (clé de cache).
- L'ordre des facteurs n'a pas de code dédié : il est signalé en `slot_missing`.
"""
from __future__ import annotations

import re
import unicodedata
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

# Contenu actif ou navigable dans un texte d'explication (rendu en Markdown par l'interface).
_UNSAFE_MARKUP = (
    # adresses : schémas web, schémas exécutables ou locaux, www.
    re.compile(r"(?<![\w])(?:https?|ftp|file|mailto|javascript|vbscript|data)\s*:|(?<![\w.])www\.", re.IGNORECASE),
    # image ou lien Markdown : `![alt]`, `[texte](cible)`
    re.compile(r"!\[|\]\("),
    # définition de lien : `[étiquette]: cible` (sauf `[E1]: texte` ordinaire)
    re.compile(r"(?m)^\s*\[(?![EGT]\d+\])[^\]]+\]:|^\s*\[[EGT]\d+\]:\s*[/#<.]"),
    # balises HTML : fermante, commentaire, doctype, instruction, ouvrante fermée, ou balise dangereuse
    re.compile(r"<[/!?]|<[A-Za-z][^<>]*>|<(?:script|iframe|img|svg|object|embed|style|link|meta|form|input|"
               r"body|html|a|video|audio|source|base|math|template|frame|frameset)\b", re.IGNORECASE),
)
_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD])
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
    """Nombres financiers et dates ISO présents dans les preuves du dossier.

    Les deux ensembles sont séparés : une date ISO (`2021-12-29`) autorise seulement
    la date complète, jamais ses composantes (`2021`, `12`, `29`) comme nombres. Les
    dates qui figurent dans un `display_value` (par exemple `max_drawdown_start`) sont
    retirées avant d'en extraire les nombres.
    """
    numbers: Set[str] = set()
    dates: Set[str] = set()
    for entry in brief.get("evidence") or []:
        shown = str(entry.get("display_value") or "")
        dates.update(m.group(0) for m in _ISO_DATE.finditer(shown))
        numbers.update(_numbers_in(_ISO_DATE.sub(" ", shown)))
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


def has_unsafe_markup(text: str) -> bool:
    """Vrai si le texte contient une URL, un lien ou une image Markdown, ou une balise HTML.

    Même règle que la validation des explications, réutilisable avant de transmettre un texte
    venu d'un profil à l'explicateur (`explanation_brief.build_profile_context`).
    """
    normalized = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return any(pattern.search(normalized) for pattern in _UNSAFE_MARKUP)


def _check_unsafe_markup(slot: str, text: str, rejections: List[Rejection]) -> None:
    """Rejette URL, lien, image Markdown et HTML (code `forbidden_term`, contrat inchangé)."""
    normalized = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    for pattern in _UNSAFE_MARKUP:
        for match in pattern.finditer(normalized):
            _reject(rejections, "forbidden_term", slot, _excerpt(normalized, match.start(), match.end()))


# Contrefactuel déclaré indisponible (P0-5). Le code affiche juste sous l'emplacement `counterfactual` le
# plus grand poids testé conforme de chaque règle en tension ou en conflit : écrire que ces poids sont
# "pas disponibles", "non calculés", "absents des preuves" contredit l'écran. Formes reconnues, sur le
# texte sans accents ni majuscules, dans une même proposition (coupée aux . ! ? ; et retours à la ligne) :
# l'objet ("poids", "contrefactuel") suivi de près d'un prédicat d'absence, ou une tournure d'absence qui
# le vise. Les fenêtres courtes évitent de rejeter "un poids plus bas rendrait [G1] conforme, mais [G7]
# reste en information manquante", phrase exacte quand un contrôle ESG n'a pas de preuve.
_OBJ = r"(?:poids|contrefactuels?)"
_GAP = r"(?:\s+[^\s.;!?]+){0,4}?"
_GAP_SHORT = r"(?:\s+[^\s.;!?]+){0,3}?"
_UNAVAILABLE_PARTICIPLE = (r"(?:disponibles?|calcule\w*|fournis?|fournies|connus?|connues|indiques?|indiquees|donnes?|"
                           r"donnees|presents?|presentes|precises?|precisees|communiques?|communiquees|"
                           r"determines?|determinees|affiches?|affichees|chiffres?|chiffrees|evalues?|evaluees)")
_COUNTERFACTUAL_UNAVAILABLE = tuple(re.compile(pattern) for pattern in (
    # "ces poids ne sont pas disponibles", "le contrefactuel n'est pas calculé", "poids non calculés"
    _OBJ + _GAP + r"\s+(?:ne\s+|n')?(?:sont|est|etait|etaient|serait|seraient)\s+(?:pas|plus|non)\s+(?:encore\s+)?"
    + _UNAVAILABLE_PARTICIPLE,
    _OBJ + _GAP + r"\s+(?:n'(?:a|ont)|ne\s+(?:a|ont))\s+pas\s+(?:pu\s+)?(?:etre\s+|ete\s+)?" + _UNAVAILABLE_PARTICIPLE,
    _OBJ + _GAP + r"\s+(?:non|pas)\s+" + _UNAVAILABLE_PARTICIPLE,
    # "poids indisponibles", "contrefactuel absent", "poids manquants"
    _OBJ + _GAP_SHORT + r"\s+(?:indisponibles?|inconnus?|inconnues|absents?|absentes|manquants?|manquantes|"
    r"introuvables?)\b",
    # "ne peuvent pas être calculés", "impossible à calculer"
    _OBJ + _GAP + r"\s+ne\s+peu(?:t|vent)\s+pas\s+etre\s+(?:calcule\w*|determine\w*|connu\w*|fourni\w*|donne\w*)",
    _OBJ + _GAP + r"\s+impossibles?\s+(?:a|de)\s+(?:calculer|determiner|connaitre|fournir|donner|chiffrer|evaluer)",
    r"impossibles?\s+(?:a|de)\s+(?:calculer|determiner|connaitre|fournir|donner|chiffrer|evaluer)" + _GAP + r"\s+"
    + _OBJ,
    r"ne\s+(?:peut|peuvent|pouvons)\s+pas\s+(?:calculer|determiner|connaitre|fournir|donner|chiffrer)"
    + _GAP_SHORT + r"\s+" + _OBJ,
    # "ces poids ne figurent pas parmi les preuves"
    _OBJ + _GAP + r"\s+(?:ne\s+|n')(?:figure|figurent|apparait|apparaissent|ressort|ressortent)\s+pas",
    # "le dossier ne donne pas le poids", "n'indique pas de poids"
    r"(?:ne|n')\s*(?:donne|donnent|fournit|fournissent|contient|contiennent|indique|indiquent|precise|precisent|"
    r"presente|presentent|mentionne|mentionnent|liste|montre|montrent)\s+pas" + _GAP_SHORT + r"\s+" + _OBJ,
    # "aucun contrefactuel", "pas de contrefactuel", "aucune information sur le poids"
    r"(?:aucun|aucune|pas\s+de|sans)\s+contrefactuel",
    r"(?:aucune?\s+(?:valeur|information|donnee|precision)|pas\s+d'information)" + _GAP_SHORT
    + r"\s+(?:sur|de|du|pour|quant)\s+(?:au?x?\s+|le\s+|les\s+|ce\s+|ces\s+)?" + _OBJ,
))
_CLAUSE = re.compile(r"[^.!?;\n]+")
_G_REFERENCE = re.compile(r"\[(G\d+)\]")


def _has_computed_counterfactual(check: Mapping[str, Any]) -> bool:
    """Vrai si le contrôle a un contrefactuel calculé que le code affiche sous l'emplacement `counterfactual`.

    Mêmes conditions que `explanation_rendering._counterfactual_lines` : statut en tension ou en conflit et
    contrefactuel présent. Un poids conforme trouvé (`compliant_at_or_below` numérique) comme "aucun poids
    testé n'est conforme" (valeur `None`) sont des résultats calculés. Un contrefactuel `None` (simulation
    indisponible ou peu fiable) n'en est pas un.
    """
    cf = check.get("counterfactual")
    if check.get("status") not in ("tension", "conflict") or not isinstance(cf, Mapping):
        return False
    bound = cf.get("compliant_at_or_below", "absent")
    if bound == "absent":
        return False
    return bound is None or (isinstance(bound, (int, float)) and not isinstance(bound, bool))


def _check_counterfactual_availability(text: str, brief: Mapping[str, Any], rejections: List[Rejection]) -> None:
    """Rejette (`forbidden_term`) un emplacement `counterfactual` qui déclare indisponible un contrefactuel calculé.

    Une proposition qui cite des contrôles n'est rejetée que si l'un d'eux a un contrefactuel calculé : dire que
    le poids d'un contrôle sans contrefactuel n'est pas disponible reste vrai. Une proposition sans renvoi
    `[G..]` est rejetée dès qu'un contrefactuel calculé existe. Sans contrefactuel calculé (simulation
    indisponible), rien n'est rejeté. Une sortie réparable : le pipeline remplace alors l'emplacement par le
    texte du gabarit.
    """
    checks = [c for c in brief.get("checks") or [] if isinstance(c, Mapping)]
    computed = {c.get("check_id") for c in checks if _has_computed_counterfactual(c)}
    if not computed:
        return
    folded = _fold(text)
    for clause in _CLAUSE.finditer(folded):
        cited = set(_G_REFERENCE.findall(text[clause.start():clause.end()]))
        if cited and not cited & computed:
            continue                 # propositions sur des contrôles sans contrefactuel (ou renvoi inconnu)
        for pattern in _COUNTERFACTUAL_UNAVAILABLE:
            match = pattern.search(clause.group(0))
            if match:
                start = clause.start() + match.start()
                _reject(rejections, "forbidden_term", "counterfactual", _excerpt(text, start, clause.start() + match.end()))
                break


def _check_text(slot: str, text: str, known: Set[str],
                numbers: Set[str], dates: Set[str], allow_registry_numbers: bool,
                max_chars: int, rejections: List[Rejection], checked: List[str],
                cited: Set[str]) -> None:
    if len(text) > max_chars:
        _reject(rejections, "too_long", slot, f"{len(text)} caractères pour {max_chars} permis : "
                + _excerpt(text, 0, 0)[:40])

    _check_unsafe_markup(slot, text, rejections)

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
        if slot == "counterfactual":
            _check_counterfactual_availability(text, brief, rejections)

    for check in brief.get("checks") or []:
        if check.get("status") in NEEDS_CITATION and check["check_id"] not in cited:
            _reject(rejections, "missing_rule_citation", "output",
                    f"[{check['check_id']}] {check.get('label_fr', '')} ({check['status']})".strip())

    return {"is_valid": not rejections, "rejections": rejections, "checked_references": checked}
