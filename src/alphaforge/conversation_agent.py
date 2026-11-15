"""Agent conversationnel (issue 78) : questions de profil et "pourquoi", un appel Bedrock sans outil.

Le code choisit les faits : l'agent ne voit qu'un dossier de conversation (`ConversationBrief`), construit
par le code a partir des preuves deja calculees. Il redige une reponse courte avec des renvois [E#] [G#] [T#],
sans aucun chiffre en clair ; le code remplace ensuite chaque renvoi par la valeur du registre. Un texte
rejete par le validateur est renvoye une seule fois au modele avec les codes de rejet ; au-dela, le pipeline
affiche la reponse du code. L'agent ne lance aucune simulation et ne propose aucune idee.

La question de l'utilisateur est transmise au modele, limitee a `MAX_QUESTION_CHARS`, et n'est jamais ecrite
dans une trace. Aucun historique de conversation n'est transmis.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping

from .bedrock_client import BedrockClient, extract_text, redact_text
from .contracts import ConversationBrief, ConversationReply
from .explainer_agent import _UNSAFE_MARKDOWN, describe_rejections
from .prompt_loader import load_prompt
from .tool_specs import AgentFailure

PROMPT_NAME = "conversation_v1"
PROMPT_VERSION = PROMPT_NAME
# Reponse courte (quatre phrases) : un plafond bas borne le cout. Pas de temperature (refusee par les modeles
# Claude recents, constate sur le compte).
INFERENCE_CONFIG = {"maxTokens": 1200}
MAX_QUESTION_CHARS = 300
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class ConversationFailure(AgentFailure):
    """L'agent conversationnel n'a pas produit de reponse exploitable : le pipeline affiche celle du code."""


def model_brief(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Copie du dossier envoyee au modele : question tronquee, aucun autre changement."""
    sent = dict(brief)
    question = brief.get("question")
    sent["question"] = question[:MAX_QUESTION_CHARS] if isinstance(question, str) else ""
    return sent


def parse_reply(text: str, brief: Mapping[str, Any], *, model_id: str,
                attempt: int) -> tuple[ConversationReply | None, str | None]:
    """Extrait {"answer": ...}. Rend (reponse, None) ou (None, probleme)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None, "Aucun objet JSON trouve dans la reponse."
    try:
        raw = json.loads(cleaned[start:end + 1], strict=False)
    except ValueError as error:
        return None, f"JSON invalide ({getattr(error, 'msg', 'erreur')})."
    answer = raw.get("answer") if isinstance(raw, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        return None, "Champ answer manquant ou vide."
    if _UNSAFE_MARKDOWN.search(answer):
        return None, "Le texte contient un lien, une image ou du HTML : ecris du texte simple, sans adresse ni balise."
    return ConversationReply(
        brief_id=brief["brief_id"], answer=answer.strip(), origin="llm",
        model_id=redact_text(model_id), prompt_version=PROMPT_VERSION, attempt=attempt,
    ), None


def reply_with_llm(
    client: BedrockClient,
    model_id: str | None,
    brief: ConversationBrief,
    validate: Callable[[ConversationReply, ConversationBrief], Any],
) -> ConversationReply:
    """Un appel, puis au plus un nouvel essai si le validateur rejette la reponse.

    Leve ``ConversationFailure`` si aucune reponse exploitable n'est obtenue. La reponse rendue peut encore
    etre invalide apres le second essai : le pipeline la valide de nouveau et affiche alors celle du code.
    """
    if not model_id:
        raise ConversationFailure("Identifiant de modele de l'agent conversationnel non configure.")
    system = load_prompt(PROMPT_NAME)
    messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": (
        "Dossier de conversation :\n" + json.dumps(model_brief(brief), ensure_ascii=False))}]}]
    last_problem = "Aucune reponse exploitable."
    for attempt in (1, 2):
        response = client.converse(model_id, messages, system=system, inference_config=INFERENCE_CONFIG)
        if response.get("stopReason") == "max_tokens":
            reply, problem = None, "Reponse tronquee (max_tokens) : quatre phrases courtes au plus."
        else:
            reply, problem = parse_reply(extract_text(response), brief, model_id=model_id, attempt=attempt)
        if reply is not None:
            try:
                verdict = validate(reply, brief)
            except Exception as error:  # un validateur defaillant ne doit pas faire planter la page
                raise ConversationFailure(f"Validateur en erreur ({type(error).__name__}).") from error
            if verdict["is_valid"] or attempt == 2:
                return reply
            problem = describe_rejections(verdict["rejections"])
        last_problem = problem or last_problem
        if attempt == 1:
            try:
                messages.append(response["output"]["message"])
            except (KeyError, TypeError) as error:
                raise ConversationFailure("Reponse Converse mal formee.") from error
            messages.append({"role": "user", "content": [{"text": (
                f"Ta reponse a ete rejetee. {last_problem} Corrige et renvoie uniquement l'objet JSON, "
                "sans chiffre en clair et avec des renvois existants.")}]})
    raise ConversationFailure(last_problem)


def render_answer(reply: Mapping[str, Any], brief: Mapping[str, Any]) -> str:
    """Renvois remplaces par ce que lit l'utilisateur (memes valeurs que l'explication)."""
    from .explanation_rendering import _Registry   # meme remplacement que le rendu de l'explication

    return _Registry(brief).substitute(str(reply.get("answer", "")))


def grounding_source(brief: Mapping[str, Any]) -> tuple[str, str]:
    """Source du controle d'ancrage : le dossier en phrases francaises, sinon son JSON (sans la question).

    Avec une idee analysee, on reprend la source de l'explication. Sans idee (question de profil), on ecrit le
    contexte du profil, les preuves, les limites, le glossaire, les fiches et ce qui manque.
    """
    without_question = {key: value for key, value in brief.items() if key != "question"}
    try:
        from . import grounding_source as gs

        if brief.get("idea"):
            lines = [gs.build_grounding_source(without_question)]
        else:
            lines = list(gs._profile_sentences(brief.get("profile_context")))
            for entry in brief.get("evidence") or []:
                lines.extend(gs._evidence_lines(entry))
            lines.extend(f"Limite : {limit.get('text', '')}" for limit in brief.get("limits") or [])
            for term in brief.get("glossary") or []:
                sentence = f"{term['term']} : {term['definition']}."
                if term.get("analogy"):
                    sentence += f" Analogie : {term['analogy']}."
                lines.append(sentence)
        for card in brief.get("cards") or []:
            text = " ".join(str(card.get(key, "")) for key in ("title", "text") if card.get(key))
            if text:
                lines.append(f"Fiche : {text}")
        lines.extend(f"Information non disponible dans ce prototype : {item}." for item in brief.get("missing") or [])
        text = "\n".join(line for line in lines if line)
        if text.strip():
            return text, "sentences"
    except Exception:  # la reecriture est une amelioration : jamais une cause d'echec
        pass
    return json.dumps(without_question, ensure_ascii=False), "json"
