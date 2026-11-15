"""Traduction déterministe d'une demande en langage naturel en idée de placement.

Aucun modèle de langage : des règles lisibles et testées (tests/test_request_parsing.py).
La fonction `parse_request` rend l'un de trois statuts :

- "refused" : la demande relève d'un sujet interdit (passage d'ordre, conseil
  personnalisé, prédiction de rendement). Ce contrôle local complète le
  garde-fou Bedrock, il ne le remplace pas ; il reste actif en mode hors ligne ;
- "clarify" : la demande est ambiguë ou incomplète. L'outil ne devine jamais :
  il rend un code de question (`reason`) et, s'il ne manque que le poids, des
  poids à proposer en un clic ;
- "idea" : une `InvestmentIdea` complète (ticker, poids visé, source des fonds).

Les textes affichés sont dans l'interface (app/ui_texts.py) : ce module ne rend
que des codes, des tickers et des nombres lus dans la demande.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Poids proposés en un clic quand seul le poids manque. Ce sont des options de
# simulation, identiques pour tous les profils, pas une recommandation.
SUGGESTED_WEIGHTS: Tuple[float, ...] = (0.05, 0.10, 0.15, 0.25)

# Codes de clarification.
NOT_AN_IDEA = "not_an_idea"
UNKNOWN_ASSET = "unknown_asset"
SEVERAL_ASSETS = "several_assets"
MISSING_WEIGHT = "missing_weight"
SEVERAL_WEIGHTS = "several_weights"
WEIGHT_OUT_OF_RANGE = "weight_out_of_range"
SEVERAL_FUNDING = "several_funding"
FUNDING_SAME_AS_ASSET = "funding_same_as_asset"
FUNDING_NOT_HELD = "funding_not_held"
MISSING_TARGET = "missing_target"

# Sujets refusés : mêmes noms que les sujets du garde-fou Bedrock (scripts/setup_guardrail.py).
ORDER_EXECUTION = "order_execution"
PERSONALIZED_ADVICE = "personalized_advice"
RETURN_PREDICTION = "return_prediction"

# Motifs appliqués au texte en minuscules et sans accents.
# Début de phrase : début du texte ou après une ponctuation forte.
_HEAD = r"(?:^|[.!?;:]\s*)\s*"
_REFUSAL_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (ORDER_EXECUTION, (
        # Verbe d'ordre en tête de phrase, au tutoiement ou au vouvoiement.
        _HEAD + r"(achete|achetes|achetez|vends|vendez|execute|executes|executez|place|places|placez"
                r"|ouvre|ouvres|ouvrez)\b",
        r"\bordres?\b",
        r"\b(ouvr|prend|pren|ferm|clotur)\w*\s+(une\s+|la\s+|ma\s+|cette\s+)?position",
        r"\bcourtier",
        r"\bcompte\s+de\s+courtage",
        r"\bconnecte(-toi|z|r)?\b.*\bcompte",
        r"\b(mon|ma|mes|notre|nos)\s+(vrai\w*\s+)?comptes?\b",
        r"\bvrais?\s+portefeuilles?\b",
        r"\b(portefeuille|compte)s?\s+(reel|vrai)",
        r"\b(achete|achetez|vends|vendez|execute|executez)\b.*\bpour\s+moi\b",
        r"\b(achete|vends)-moi\b",
    )),
    (RETURN_PREDICTION, (
        r"\b(va|vont)(-t-(il|elle))?\s+(rapporter|doubler|tripler|monter|baisser|remonter|grimper|chuter"
        r"|exploser|faire)\b",
        r"\b(vaudra|vaudront|rapportera|rapporteront)\b",
        r"\bgarant(ir|is|it|ie|i)\b",
        r"\b(prevision|prevoir|predi(s|re|ction))",
        r"\bcombien\s+(vais-je|je\s+vais|vas-tu\s+me\s+faire)\s+gagner",
        r"\b(rendements?|performances?|cours|prix)\s+(futurs?|a\s+venir|attendus?)\b",
        r"\bquel(le)?s?\s+sera\b",
        r"\bquel(le)?s?\s+(rendement|performance|cours|prix)\s+(aura|auront|fera|feront)\b",
        r"\bl'an\s+prochain\b|\bl'annee\s+prochaine\b",
    )),
    (PERSONALIZED_ADVICE, (
        r"\b(dois-je|devrais-je|je\s+devrais|que\s+dois-je)\b",
        r"\b(conseille|recommande)s?-moi\b",
        r"\bque\s+me\s+(conseilles|recommandes|conseillez|recommandez)\b",
        r"\bdis-moi\s+(quoi|ce\s+qu'il\s+faut)\b",
        r"\bquoi\s+acheter\b",
        r"\bcomment\s+en\s+profiter\b",
        r"\bvu\s+ma\s+situation\b",
        r"\bmeilleur\s+(placement|actif|titre)\b",
    )),
)

# Mots qui introduisent le titre vendu pour financer l'idée.
_FUNDING_MARKERS = (
    r"\ben\s+vendant\b", r"\bvendant\b", r"\bvendre\b", r"\ben\s+puisant\s+dans\b", r"\ben\s+reduisant\b",
    r"\bfinance[es]*\s+(par|avec|depuis)\b", r"\bdepuis\b", r"\ba\s+partir\s+de\b", r"\bau\s+lieu\s+de\b",
    r"\bpris\s+sur\b", r"\bpreleve[es]*\s+sur\b",
)
_PRO_RATA = r"\bprorata\b"
# Un nombre collé à une lettre, un point, une virgule ou un tiret n'est pas lu (1e2, 10.5.3) ;
# le signe moins est capturé pour refuser un poids négatif.
_PERCENT = re.compile(r"(?<![\w.,\-])(-?\d+(?:[.,]\d+)?)\s*(?:%|pour\s*cent\b|pourcent\b)")
# Liaison entre deux titres vendus ("SPY et XIU.TO").
_FUNDING_LINK = re.compile(r"\s*(,|et|ou|puis)?\s*(du\s+|de\s+|des\s+|d')?")
# Jeton qui ressemble à un ticker (majuscules, éventuellement suffixe .TO ou -USD).
_TICKER_LIKE = re.compile(r"(?<![A-Za-z0-9.\-])([A-Z]{2,5}(?:[.\-][A-Z]{2,3})?)(?![A-Za-z0-9\-])")
# Mots de premier rang trop génériques pour servir d'alias.
_ALIAS_STOPWORDS = {"ishares", "spdr", "vanguard", "invesco", "bmo", "canadian", "royal", "alimentation",
                    "constellation", "procter", "johnson", "toronto-dominion"}
# Alias usuels absents des noms officiels.
_EXTRA_ALIASES = {"btc": "BTC-USD", "bitcoin": "BTC-USD", "eth": "ETH-USD", "ethereum": "ETH-USD",
                  "google": "GOOGL", "couche-tard": "ATD.TO", "manulife": "MFC.TO"}


@dataclass(frozen=True)
class ParsedRequest:
    """Résultat de l'analyse d'une demande. `idea` n'est rempli que pour le statut "idea"."""
    status: str
    reason: Optional[str] = None
    idea: Optional[Dict[str, object]] = None
    tickers: Tuple[str, ...] = ()
    target_weight: Optional[float] = None
    funding_ticker: Optional[str] = None
    unknown_tokens: Tuple[str, ...] = ()
    suggested_weights: Tuple[float, ...] = ()


def normalize(text: str) -> str:
    """Minuscules sans accents, même longueur que le texte d'origine (positions conservées)."""
    chars = []
    for char in text:
        base = unicodedata.normalize("NFD", char)[0]
        chars.append(base.lower() if len(base.lower()) == 1 else char)
    return "".join(chars).replace("\u2019", "'")


def screen_request(text: str) -> Optional[str]:
    """Sujet interdit détecté dans la demande, ou None."""
    lowered = normalize(text)
    for topic, patterns in _REFUSAL_PATTERNS:
        if any(re.search(pattern, lowered) for pattern in patterns):
            return topic
    return None


def build_aliases(universe: Iterable[Mapping[str, str]]) -> Dict[str, str]:
    """alias -> ticker. Tickers complets et sans suffixe, nom complet, premier mot du nom (actions)."""
    aliases: Dict[str, str] = {}
    tickers = set()
    for asset in universe:
        ticker = str(asset["ticker"])
        tickers.add(ticker)
        aliases[ticker] = ticker
        root = re.split(r"[.\-]", ticker)[0]
        aliases.setdefault(root, ticker)
        name = normalize(str(asset.get("name") or "")).strip()
        if name:
            aliases.setdefault(name, ticker)
            first = name.split()[0].strip(",")
            if (asset.get("asset_class") in ("equity", "crypto") and len(first) >= 4
                    and first not in _ALIAS_STOPWORDS):
                aliases.setdefault(first, ticker)
    for alias, ticker in _EXTRA_ALIASES.items():
        if ticker in tickers:
            aliases.setdefault(alias, ticker)
    return aliases


def _alias_matcher(alias: str) -> Tuple[re.Pattern, bool]:
    """Motif d'un alias et s'il s'applique au texte d'origine (sensible à la casse).

    Un ticker court (3 lettres ou moins avant le suffixe, comme PG ou XIU) n'est reconnu
    qu'en majuscules, pour ne pas confondre un mot courant avec un actif.
    """
    is_ticker = alias.upper() == alias and any(char.isalpha() for char in alias)
    case_sensitive = is_ticker and len(re.split(r"[.\-]", alias)[0]) <= 3
    body = re.escape(alias if case_sensitive else alias.lower())
    return re.compile(r"(?<![A-Za-z0-9.\-])" + body + r"(?![A-Za-z0-9\-]|\.[A-Za-z])"), case_sensitive


def find_assets(text: str, aliases: Mapping[str, str]) -> List[Tuple[int, int, str]]:
    """Mentions d'actifs (début, fin, ticker), sans chevauchement, dans l'ordre du texte."""
    lowered = normalize(text)
    found: List[Tuple[int, int, str]] = []
    for alias, ticker in aliases.items():
        pattern, case_sensitive = _alias_matcher(alias)
        for match in pattern.finditer(text if case_sensitive else lowered):
            found.append((match.start(), match.end(), ticker))
    # Les mentions les plus longues gagnent (XIU.TO plutôt que XIU).
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: List[Tuple[int, int, str]] = []
    for start, end, ticker in found:
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end, ticker))
    return kept


def _weights(text: str) -> List[float]:
    """Poids cités, en fraction (25 % -> 0.25), sans doublon, signe conservé."""
    values = []
    for raw in _PERCENT.findall(text):
        value = round(float(raw.replace(",", ".")) / 100, 4)
        if value not in values:
            values.append(value)
    return values


def _is_whole_percent(weight: float) -> bool:
    return abs(weight * 100 - round(weight * 100)) < 1e-9


def _split_targets(lowered: str, mentions: List[Tuple[int, int, str]]) -> Tuple[List[str], List[str]]:
    """Cibles et titres vendus. Le premier actif cité après un marqueur de financement le finance ;
    les actifs qui le suivent, reliés par "et", "ou" ou une virgule, aussi."""
    marker_ends = sorted({match.end() for pattern in _FUNDING_MARKERS for match in re.finditer(pattern, lowered)})
    funding_positions = set()
    for marker_end in marker_ends:
        following = [position for position, mention in enumerate(mentions) if mention[0] >= marker_end]
        if not following:
            continue
        position = following[0]
        funding_positions.add(position)
        while position + 1 < len(mentions) and _FUNDING_LINK.fullmatch(
                lowered[mentions[position][1]:mentions[position + 1][0]]):
            position += 1
            funding_positions.add(position)
    targets: List[str] = []
    funders: List[str] = []
    for position, (_, _, ticker) in enumerate(mentions):
        bucket = funders if position in funding_positions else targets
        if ticker not in bucket:
            bucket.append(ticker)
    return targets, funders


def parse_request(text: str, universe: Sequence[Mapping[str, str]],
                  held_tickers: Optional[Sequence[str]] = None) -> ParsedRequest:
    """Analyse une demande. `held_tickers` : titres détenus, pour vérifier la source des fonds."""
    topic = screen_request(text)
    if topic:
        return ParsedRequest(status="refused", reason=topic)

    lowered = normalize(text)
    mentions = find_assets(text, build_aliases(universe))
    targets, funders = _split_targets(lowered, mentions)
    weights = _weights(text)
    weight = weights[0] if len(weights) == 1 else None
    known = {str(asset["ticker"]) for asset in universe}
    unknown = tuple(token for token in dict.fromkeys(_TICKER_LIKE.findall(text))
                    if token not in known and token not in {ticker.split(".")[0] for ticker in known}
                    and token not in {ticker.split("-")[0] for ticker in known})

    def clarify(reason: str, **extra) -> ParsedRequest:
        return ParsedRequest(status="clarify", reason=reason, tickers=tuple(targets), target_weight=weight,
                             funding_ticker=funders[0] if len(funders) == 1 else None,
                             unknown_tokens=unknown, **extra)

    if not targets:
        if funders and not unknown:
            return clarify(MISSING_TARGET)
        if unknown or weights:
            return clarify(UNKNOWN_ASSET)
        return clarify(NOT_AN_IDEA)
    if len(targets) > 1:
        return clarify(SEVERAL_ASSETS)
    if len(weights) > 1:
        return clarify(SEVERAL_WEIGHTS)
    if len(funders) > 1:
        return clarify(SEVERAL_FUNDING)
    funding_ticker = funders[0] if funders and not re.search(_PRO_RATA, lowered) else None
    if funding_ticker == targets[0]:
        return clarify(FUNDING_SAME_AS_ASSET)
    if funding_ticker and held_tickers is not None and funding_ticker not in held_tickers:
        return clarify(FUNDING_NOT_HELD)
    if weight is None:
        return clarify(MISSING_WEIGHT, suggested_weights=SUGGESTED_WEIGHTS)
    if not 0.01 <= weight <= 1 or not _is_whole_percent(weight):
        # Poids entiers de 1 % à 100 % seulement ; une décimale propose l'arrondi en un clic.
        rounded = min(100, max(1, round(weight * 100))) / 100
        suggestion = (rounded,) if weight > 0 and not _is_whole_percent(weight) else ()
        return clarify(WEIGHT_OUT_OF_RANGE, suggested_weights=suggestion)
    idea = {
        "ticker": targets[0],
        "target_weight": weight,
        "funding_source": "from_ticker" if funding_ticker else "pro_rata",
        "funding_ticker": funding_ticker,
    }
    return ParsedRequest(status="idea", idea=idea, tickers=(targets[0],), target_weight=weight,
                         funding_ticker=funding_ticker)
