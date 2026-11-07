"""Deliberation : calibration de la confiance, seuil d'abstention, choix du mode.

Portage fidele des cellules 27 et 32 du notebook. C'est ici que le systeme decide de repondre ou
de se taire — jamais le modele. Le service d'inference propose du texte ; ce module arrete le mode.

Specification : docs/spec-module-ra.md, section 6.4.
"""

from __future__ import annotations

import math
import re
from typing import Any

from rda.ra.recherche import Candidat

MODE_EXTRACTIF = "EXTRACTIF"
MODE_GENERATIF = "GENERATIF"
MODE_ABSTENTION = "ABSTENTION"
MODE_NEUTRALISATION = "NEUTRALISATION"
MODE_CONVERSATION = "CONVERSATION"
# Description de la photo du technicien. Distinct des autres a dessein : elle ne cite aucune
# source et n'engage que ce que le modele croit voir. La confondre avec une reponse
# documentaire serait presenter une observation comme une consigne de maintenance.
MODE_DESCRIPTION = "DESCRIPTION"

# Poids de la calibration (cellule 27) : la part d'appui penalise le candidat isole. Une source
# unique bien notee, sans corroboration, inspire moins confiance que trois sources concordantes.
POIDS_MEILLEUR = 0.7
POIDS_APPUI = 0.3
NB_APPUI = 3

# Ecart assume avec le notebook (cellule 31). Sa derniere alternative s'ecrivait
# « ignore\s+(all|previous)\s+instructions », qui exige « instructions » juste apres « all » ou
# « previous » et laisse donc passer « ignore all previous instructions » — la formulation
# d'injection la plus repandue. Les deux qualificatifs sont ici facultatifs et cumulables.
RE_INJECTION = re.compile(
    r"(ignore[sz]?\s+(les\s+|toutes\s+les\s+)?(instructions|consignes|règles)|"
    r"oublie[sz]?\s+(tout|les)|tu\s+es\s+(maintenant|désormais)|system\s*:|"
    r"nouvelle\s+consigne|ignore\s+(all\s+)?(previous\s+)?instructions)",
    re.I,
)

# Longueur de l'extrait joint a chaque citation : de quoi juger sans noyer l'ecran.
EXTRAIT_CITATION = 450

RE_CONVERSATION = re.compile(
    r"^\s*(bonjour|bonsoir|salut|hello|coucou|merci( beaucoup)?|ok|d'accord|ça va\s*\??|"
    r"au revoir)[\s!.?]*$",
    re.I,
)


def sigmoide(x: float) -> float:
    """Sigmoide numeriquement stable : le reclasseur rend des logits non bornes."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exponentielle = math.exp(x)
    return exponentielle / (1.0 + exponentielle)


def calibrer(candidats: list[Candidat], k_final: int) -> tuple[list[Candidat], float]:
    """Trie par score de reclassement et calcule la confiance (cellule 27).

    confiance = 0,7 x sigmoide(meilleur) + 0,3 x moyenne des sigmoides des trois premiers.
    """
    if not candidats:
        return [], 0.0

    retenus = sorted(
        candidats,
        key=lambda c: c.score_reclassement if c.score_reclassement is not None else -math.inf,
        reverse=True,
    )[:k_final]

    meilleur = sigmoide(retenus[0].score_reclassement or 0.0)
    if len(retenus) >= NB_APPUI:
        appui = sum(sigmoide(c.score_reclassement or 0.0) for c in retenus[:NB_APPUI]) / NB_APPUI
    else:
        appui = meilleur
    return retenus, float(POIDS_MEILLEUR * meilleur + POIDS_APPUI * appui)


def seuil_abstention(famille: str, seuils: dict[str, float]) -> float:
    """Seuil de la famille, ou seuil par defaut.

    tau = (C_err - C_sil) / (G + C_err) : l'infrastructure est le perimetre ou l'erreur coute le
    plus cher, donc celui ou le systeme se tait le plus tot.
    """
    return float(seuils.get(famille, seuils.get("DEFAUT", 0.65)))


def est_injection(question: str) -> bool:
    """Detecte une tentative de detournement des consignes dans la question."""
    return bool(RE_INJECTION.search(question))


def est_civilite(question: str) -> bool:
    """Detecte une formule de politesse seule, qui n'appelle aucune recherche."""
    return bool(RE_CONVERSATION.match(question))


def numeros_cites(texte: str) -> set[int]:
    """Numeros de source cites sous la forme [n]."""
    return {int(n) for n in re.findall(r"\[(\d+)\]", texte)}


def reponse_ancree(texte: str, nb_sources: int) -> bool:
    """Vrai si chaque [n] du texte designe une source reellement fournie (cellule 32).

    Une reponse sans aucune citation, ou qui cite une source inexistante, n'est pas etayee : elle
    ne doit jamais etre restituee telle quelle. L'appelant retombe alors en mode extractif.
    """
    numeros = numeros_cites(texte)
    return bool(numeros) and all(1 <= n <= nb_sources for n in numeros)


def construire_citations(
    retenus: list[Candidat], elements: list[dict[str, Any]], question: str = ""
) -> list[dict[str, Any]]:
    """Citations restituees au technicien, numerotees a partir de 1 (cellule 32).

    Chaque citation porte son propre extrait, nettoye et recentre sur la question. Sans lui, une
    source sans illustration n'est qu'un titre et un numero de page : le technicien ne peut pas
    verifier ce qu'elle dit sans ouvrir le manuel papier, ce qui vide la citation de son sens.
    """
    from rda.ra.lisibilite import extraire_pertinent
    citations = []
    for rang, candidat in enumerate(retenus, start=1):
        element = elements[candidat.position]
        citations.append(
            {
                "rang": rang,
                "id": element["id"],
                "type": element["type"],
                "reference": element["reference"],
                "page": element["page_debut"],
                "image": element["chemin_image"],
                "titre_doc": element["titre_doc"],
                "indice": element["indice"],
                "extrait": extraire_pertinent(
                    element["texte"], question, max_caracteres=EXTRAIT_CITATION
                ),
                **{nom: round(valeur, 4) for nom, valeur in candidat.scores.items()},
            }
        )
    return citations
