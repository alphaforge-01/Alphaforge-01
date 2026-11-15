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

# Statuts ajoutés pour le dialogue (lot 1, issue #78) : une réponse du code, ou une idée à
# confirmer en un clic quand le poids a été lu sans "%" (jamais d'analyse sur une supposition).
ANSWER = "answer"
CONFIRM = "confirm"
# Réponses produites par le code (aucun texte de modèle).
ANSWER_GREETING = "greeting"          # salutation ou "que peux-tu faire ?"
ANSWER_PORTFOLIO = "portfolio"        # "quels sont mes actifs ?" : positions du portefeuille fictif
ANSWER_DEFINITION = "definition"      # "c'est quoi la volatilité ?" : glossaire du projet
ANSWER_OUT_OF_SCOPE = "out_of_scope"  # le reste : ce que l'outil sait faire, avec des exemples
# Raisons des nouveaux cas.
FOLLOW_UP = "follow_up"                  # "et à 10 % ?" : même actif et même financement que la dernière idée
RELATIVE_WEIGHT = "relative_weight"      # "5 % de plus" : on demande le poids total, on ne calcule pas l'écart
WEIGHT_TO_CONFIRM = "weight_to_confirm"  # "0,25", "un quart" : poids à confirmer

# Sujets refusés : mêmes noms que les sujets du garde-fou Bedrock (scripts/setup_guardrail.py).
ORDER_EXECUTION = "order_execution"
PERSONALIZED_ADVICE = "personalized_advice"
RETURN_PREDICTION = "return_prediction"

# Motifs appliqués au texte en minuscules et sans accents.
# Début de phrase : début du texte ou après une ponctuation forte. Une salutation en tête
# ("bonjour, achète TSLA") est retirée avant un second contrôle (voir `screen_request`).
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
        # Ordre d'achat relié par une conjonction ("..., et achète TSLA").
        r",\s*(et|puis|alors|ensuite)\s+(achete|achetes|achetez)\b",
        # "je vends tout ?" : une transaction réelle demandée en passant (constaté à l'audit de l'agent).
        r"\bje\s+(vends|achete)\s+(tout|maintenant|immediatement)\b",
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
        # Prémisse d'avenir dans une question ("pourquoi la perte sera plus forte demain ?").
        r"\b(sera|seront)\b.*\b(demain|bientot|prochain\w*)\b",
        r"\b(va|vont)\s+(augmenter|diminuer|empirer|s'aggraver)\b",
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
        # "faut-il vendre ?", "que faudrait-il acheter ?", "quel titre choisir ?" (constaté à l'audit de l'agent).
        r"\b(faut-il|faudrait-il)\s+(acheter|vendre|investir|garder|choisir)\b",
        r"\bquel(le)?s?\s+(titre|actif|action|placement|fonds)s?\s+(choisir|prendre|acheter)\b",
        r"\b(que|quoi)\s+(vendre|choisir)\b",
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


# Sigles courants qui ressemblent à un ticker sans en être un.
_NOT_TICKERS = {"ESG", "OK", "CAD", "USD", "FNB", "ETF", "TSX", "IA", "AI", "PDF", "FAQ"}

# --- Dialogue : intentions reconnues sans modèle (texte en minuscules, sans accents) -------------
_GREETING = re.compile(r"^\W*(hey|hi|hello|salut|bonjour|bonsoir|coucou|yo|allo|bjr|slt)\b")
_HELP = re.compile(
    r"\b(aide|help)\b|que\s+(peux|sais|sait|pouvez|savez)[- ]?(tu|vous)\s+faire"
    r"|qu'?est-ce\s+que\s+(tu|vous)\s+(peux|pouvez|sais|savez)\s+faire|comment\s+(ca|tu)\s+(marche|fonctionne)"
    r"|a\s+quoi\s+(tu\s+)?(sers|servez)|(qui|que)\s+es-tu|tu\s+fais\s+quoi|comment\s+(t'|vous\s+)?utiliser")
_PORTFOLIO = re.compile(
    r"\b(mes|mon|ma)\s+(actifs?|positions?|placements?|titres?|portefeuilles?|investissements?|avoirs?|actions)\b"
    r"|\bqu'?est-ce\s+que\s+(je|j')\s*(detiens|possede|ai)\b|\bque\s+(je\s+)?(detiens|possede)\b"
    r"|\bje\s+(detiens|possede|ai)\s+quoi\b|\bcomposition\b")
_DEFINITION_ASK = re.compile(
    r"c'?est\s+quoi|qu'?est-ce\s+(que|qu')|que\s+(veut|veulent)\s+dire|veut\s+dire\s+quoi|que\s+signifie"
    r"|signifie\s+quoi|definition|defini[rst]|expliqu|comprends?\s+pas|ca\s+mesure\s+quoi")
# Mots qui désignent un terme du glossaire (`reference/glossary.json`, identifiants T1 à T11).
# Les définitions restent dans le glossaire : ici, seulement de quoi reconnaître la question.
TERM_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "T1": (r"volatil", r"\bvariations?\b", r"\bfluctuations?\b"),
    "T2": (r"perte\s+max", r"drawdown", r"plus\s+forte\s+baisse"),
    "T3": (r"concentr", r"diversif"),
    "T4": (r"part\s+defensive", r"defensi"),
    "T5": (r"correl",),
    "T6": (r"\besg\b", r"critere\s+esg", r"durabilit", r"\bethique"),
    "T7": (r"recuperation", r"duree\s+de\s+reprise"),
    "T8": (r"taux\s+de\s+change", r"risque\s+de\s+change", r"exposition\s+(au|aux)\s+(change|devises?)",
           r"\bdevises?\b"),
    "T9": (r"survivant", r"biais\s+de\s+survie"),
    "T10": (r"contre-?factuel", r"poids\s+conforme"),
    "T11": (r"\bhypotheses?\b",),
}
# Écart relatif ("5 % de plus", "réduis de 5 %") : jamais converti en poids total.
_RELATIVE = re.compile(r"\b(de\s+plus|de\s+moins|en\s+plus|en\s+moins|encore|supplementaire|redui|baiss|augment"
                       r"|ajout|retir|enleve|diminu|vend)\w*")
# Relance sur la dernière idée : "et à 10 % ?", "plutôt 15 %", "et si c'était 5 % ?".
_FOLLOW_UP = re.compile(r"^\W*(et|plutot|ou|alors|mais|sinon)\b|\bet\s+si\b|\ba\s+la\s+place\b|\bplutot\b")
# Poids écrits sans "%" : décimales de 0 à 1 et fractions en toutes lettres.
_DECIMAL = re.compile(r"(?<![\w.,\-])(0[.,]\d{1,4}|1[.,]0{1,4})(?![\w.,]|\s*(%|pour\s*cent|pourcent))")
_WORD_WEIGHTS: Tuple[Tuple[str, float], ...] = (
    (r"\btrois\s+quarts?\b", 0.75), (r"\bun\s+quart\b", 0.25), (r"\b(la\s+)?moitie\b", 0.5),
    (r"\bun\s+tiers\b", 0.33), (r"\bun\s+cinquieme\b", 0.2), (r"\bun\s+dixieme\b", 0.1),
)
# Entier seul, sans "%", avant ou après un actif ("25 NVDA") : on propose 25 % sans le supposer.
_BARE_INTEGER = re.compile(r"(?<![\w.,\-%])(100|[1-9]\d?)(?![\w.,%]|\s*(%|pour\s*cent|pourcent|ans?\b))")


@dataclass(frozen=True)
class ParsedRequest:
    """Résultat de l'analyse d'une demande.

    `idea` est rempli pour les statuts "idea" et "confirm" (à confirmer en un clic) ;
    `answer_kind` et `term_id` pour le statut "answer" (réponse produite par le code).
    """
    status: str
    reason: Optional[str] = None
    idea: Optional[Dict[str, object]] = None
    tickers: Tuple[str, ...] = ()
    target_weight: Optional[float] = None
    funding_ticker: Optional[str] = None
    unknown_tokens: Tuple[str, ...] = ()
    suggested_weights: Tuple[float, ...] = ()
    answer_kind: Optional[str] = None
    term_id: Optional[str] = None


def normalize(text: str) -> str:
    """Minuscules sans accents, même longueur que le texte d'origine (positions conservées)."""
    chars = []
    for char in text:
        base = unicodedata.normalize("NFD", char)[0]
        chars.append(base.lower() if len(base.lower()) == 1 else char)
    return "".join(chars).replace("\u2019", "'")


def screen_request(text: str) -> Optional[str]:
    """Sujet interdit détecté dans la demande, ou None.

    Contrôlé deux fois : sur le texte entier, puis sans la salutation de tête, pour qu'un
    « bonjour, achète TSLA » reste un ordre refusé sans élargir le début de phrase à toute virgule.
    """
    lowered = normalize(text)
    variants = [lowered]
    greeting = _GREETING.match(lowered)
    if greeting:
        variants.append(re.sub(r"^[\s,;:!.-]+", "", lowered[greeting.end():]))
    for topic, patterns in _REFUSAL_PATTERNS:
        if any(re.search(pattern, variant) for pattern in patterns for variant in variants):
            return topic
    return None


def _is_short(lowered: str) -> bool:
    """Message de trois mots ou moins ("volatilité ?", "10 %")."""
    return len(re.findall(r"\w+", lowered)) <= 3


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


def _soft_weights(text: str, lowered: str) -> List[float]:
    """Poids écrits sans "%" ("0,25", "un quart"), en fraction, sans doublon. À confirmer, jamais appliqués."""
    values: List[float] = []
    for match in _DECIMAL.finditer(text):
        value = round(float(match.group(1).replace(",", ".")), 4)
        if 0 < value <= 1 and value not in values:
            values.append(value)
    for pattern, value in _WORD_WEIGHTS:
        if re.search(pattern, lowered) and value not in values:
            values.append(value)
            break  # "trois quarts" passe avant "un quart"
    return values


def _bare_integers(text: str) -> List[int]:
    return list(dict.fromkeys(int(raw[0]) for raw in _BARE_INTEGER.findall(text)))


def find_term(lowered: str) -> Optional[str]:
    """Terme du glossaire cité en premier dans le texte, ou None."""
    found = []
    for term_id, patterns in TERM_KEYWORDS.items():
        positions = [match.start() for pattern in patterns for match in re.finditer(pattern, lowered)]
        if positions:
            found.append((min(positions), term_id))
    return min(found)[1] if found else None


def conversation_intent(lowered: str) -> ParsedRequest:
    """Message sans idée : réponse du code (définition, portefeuille, accueil) ou hors périmètre.

    Ordre : une définition avec un terme reconnu passe avant tout ("explique la volatilité de mon
    portefeuille" est une définition), puis le portefeuille, une demande de définition sans terme
    connu, l'accueil et l'aide ; le reste reçoit la liste de ce que l'outil sait faire.
    """
    term = find_term(lowered)
    asks_definition = bool(_DEFINITION_ASK.search(lowered))
    if term and (asks_definition or _is_short(lowered)):
        return ParsedRequest(status=ANSWER, answer_kind=ANSWER_DEFINITION, term_id=term)
    if _PORTFOLIO.search(lowered):
        return ParsedRequest(status=ANSWER, answer_kind=ANSWER_PORTFOLIO)
    if asks_definition and term is None and not _HELP.search(lowered):
        return ParsedRequest(status=ANSWER, answer_kind=ANSWER_DEFINITION)
    if _GREETING.search(lowered) or _HELP.search(lowered):
        return ParsedRequest(status=ANSWER, answer_kind=ANSWER_GREETING)
    return ParsedRequest(status=ANSWER, answer_kind=ANSWER_OUT_OF_SCOPE, reason=NOT_AN_IDEA)


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


def _follow_up(text: str, lowered: str, weights: List[float], soft: List[float],
                previous_idea: Optional[Mapping[str, object]]) -> Optional[ParsedRequest]:
    """ "Et à 10 % ?" après une analyse : même actif et même financement que la dernière idée.

    Un poids avec "%" donne l'idée directement (l'actif est celui que l'utilisateur vient de voir) ;
    un poids sans "%" ("et 0,1 ?") est seulement proposé, à confirmer.
    """
    if not previous_idea or not previous_idea.get("ticker"):
        return None
    if not (_FOLLOW_UP.search(lowered) or _is_short(lowered)):
        return None
    if len(weights) + len(soft) != 1:
        return None
    ticker = str(previous_idea["ticker"])
    funding_source = str(previous_idea.get("funding_source") or "pro_rata")
    funding_ticker = previous_idea.get("funding_ticker") if funding_source == "from_ticker" else None
    if _RELATIVE.search(lowered):
        # "Réduis de 5 %", "5 % de plus" : un écart, pas un poids total. Rien n'est calculé ni deviné.
        return ParsedRequest(status="clarify", reason=RELATIVE_WEIGHT, tickers=(ticker,),
                             funding_ticker=funding_ticker, suggested_weights=SUGGESTED_WEIGHTS)
    weight = (weights or soft)[0]
    if not 0.01 <= weight <= 1 or not _is_whole_percent(weight):
        rounded = min(100, max(1, round(weight * 100))) / 100
        return ParsedRequest(status="clarify", reason=WEIGHT_OUT_OF_RANGE, tickers=(ticker,), target_weight=weight,
                             funding_ticker=funding_ticker,
                             suggested_weights=(rounded,) if weight > 0 and not _is_whole_percent(weight) else ())
    idea = {"ticker": ticker, "target_weight": weight, "funding_source": funding_source,
            "funding_ticker": funding_ticker}
    # Toujours à confirmer : l'actif et le financement viennent du contexte, pas du message.
    return ParsedRequest(status=CONFIRM, reason=FOLLOW_UP, idea=idea, tickers=(ticker,), target_weight=weight,
                         funding_ticker=funding_ticker)


def parse_request(text: str, universe: Sequence[Mapping[str, str]],
                  held_tickers: Optional[Sequence[str]] = None,
                  previous_idea: Optional[Mapping[str, object]] = None) -> ParsedRequest:
    """Analyse une demande.

    `held_tickers` : titres détenus, pour vérifier la source des fonds. `previous_idea` : dernière
    idée analysée, pour les relances ("et à 10 % ?") ; seule l'idée structurée sert de contexte,
    jamais le texte des messages précédents.
    """
    topic = screen_request(text)
    if topic:
        return ParsedRequest(status="refused", reason=topic)

    lowered = normalize(text)
    mentions = find_assets(text, build_aliases(universe))
    targets, funders = _split_targets(lowered, mentions)
    weights = _weights(text)
    weight = weights[0] if len(weights) == 1 else None
    soft = [] if weights else _soft_weights(text, lowered)
    known = {str(asset["ticker"]) for asset in universe}
    unknown = tuple(token for token in dict.fromkeys(_TICKER_LIKE.findall(text))
                    if token not in known and token not in {ticker.split(".")[0] for ticker in known}
                    and token not in {ticker.split("-")[0] for ticker in known} and token not in _NOT_TICKERS)

    def clarify(reason: str, **extra) -> ParsedRequest:
        return ParsedRequest(status="clarify", reason=reason, tickers=tuple(targets), target_weight=weight,
                             funding_ticker=funders[0] if len(funders) == 1 else None,
                             unknown_tokens=unknown, **extra)

    if not targets:
        if funders and not unknown:
            return clarify(MISSING_TARGET)
        if not unknown and not funders:
            follow = _follow_up(text, lowered, weights, soft, previous_idea)
            if follow is not None:
                return follow
        if unknown or weights:
            return clarify(UNKNOWN_ASSET)
        return conversation_intent(lowered)
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
        if len(soft) == 1:
            # "0,25 NVIDIA", "un quart en NVIDIA" : idée proposée, à confirmer en un clic.
            idea = {"ticker": targets[0], "target_weight": soft[0],
                    "funding_source": "from_ticker" if funding_ticker else "pro_rata",
                    "funding_ticker": funding_ticker}
            if _is_whole_percent(soft[0]):
                return ParsedRequest(status=CONFIRM, reason=WEIGHT_TO_CONFIRM, idea=idea, tickers=(targets[0],),
                                     target_weight=soft[0], funding_ticker=funding_ticker)
        if len(soft) == 1:
            # "0,333 NVDA" : décimale non entière en pourcentage, l'arrondi est proposé en premier.
            first = min(100, max(1, round(soft[0] * 100))) / 100
            options = (first,) + tuple(option for option in SUGGESTED_WEIGHTS if option != first)
            return clarify(MISSING_WEIGHT, suggested_weights=options)
        integers = [value for value in _bare_integers(text) if 1 <= value <= 100]
        if len(integers) == 1:
            # "25 NVDA" reste une question : le poids lu est proposé en premier, jamais supposé.
            first = integers[0] / 100
            options = (first,) + tuple(option for option in SUGGESTED_WEIGHTS if option != first)
            return clarify(MISSING_WEIGHT, suggested_weights=options)
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
