"""Recherche hybride multimodale a quatre canaux, filtree avant le scoring.

Portage fidele de la cellule 25 du notebook. Le point essentiel : le filtre d'habilitation, de
validite datee et d'equipement est applique **avant** le scoring, par un masque booleen. Un
element hors perimetre n'est jamais note, donc jamais classe, donc jamais fusionne. Filtrer apres
coup laisserait fuiter l'existence des documents par les scores.

Les fonctions de ce module sont pures : elles recoivent les scores des canaux deja calcules. Les
appels aux encodeurs vivent dans « agent.py », ce qui rend la fusion testable sans service.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

import numpy as np

CANAUX = ("dense", "lexical", "image_texte", "image_image")


@dataclass
class Candidat:
    """Un element retenu par la fusion, avec le detail de ses scores par canal."""

    position: int
    score_fusion: float
    scores: dict[str, float] = field(default_factory=dict)
    score_reclassement: float | None = None


def applicable(element: dict[str, Any], date_reference: str) -> bool:
    """Vrai si l'element est en vigueur a la date de reference (cellule 25).

    Une version pas encore entree en vigueur, ou deja abrogee, n'est pas citable : la reponse
    doit refleter le texte applicable au moment de la question.
    """
    date_effet = element.get("date_effet")
    if date_effet and date_reference < str(date_effet):
        return False
    date_abrogation = element.get("date_abrogation")
    if date_abrogation and date_reference >= str(date_abrogation):
        return False
    return True


def masque_autorise(
    elements: list[dict[str, Any]],
    *,
    groupes: Iterable[str] | None,
    equipement: str | None = None,
    types: Iterable[str] | None = None,
    date_reference: str | None = None,
) -> np.ndarray:
    """Masque booleen des elements que cet agent a le droit de voir, a cette date.

    « groupes = None » signifie « aucun filtre d'habilitation » : reserve aux usages
    d'administration et d'evaluation, jamais a une requete d'agent.
    """
    date_reference = date_reference or date.today().isoformat()
    groupes_autorises = None if groupes is None else set(groupes)
    types_retenus = None if types is None else set(types)

    return np.array(
        [
            (groupes_autorises is None or element["groupe"] in groupes_autorises)
            and (equipement is None or element["equipement_id"] == equipement)
            and (types_retenus is None or element["type"] in types_retenus)
            and applicable(element, date_reference)
            for element in elements
        ],
        dtype=bool,
    )


def classer(scores: np.ndarray, masque: np.ndarray, k: int) -> list[int]:
    """Les k meilleures positions parmi les elements autorises.

    Les positions interdites sont mises a moins l'infini puis ecartees : elles ne peuvent pas
    remonter, meme si tous les scores autorises sont negatifs.
    """
    masques = np.where(masque, scores, -np.inf)
    return [int(i) for i in np.argsort(-masques)[:k] if np.isfinite(masques[i])]


def fusionner(
    listes: dict[str, list[int]],
    scores_par_canal: dict[int, dict[str, float]],
    *,
    poids: dict[str, float],
    rrf_k: int,
    k: int,
) -> list[Candidat]:
    """Fusion de rang reciproque ponderee (cellule 25).

    score(i) = somme sur les canaux de poids / (rrf_k + rang). La fusion par rang, et non par
    score, permet de melanger des canaux dont les echelles n'ont rien de comparable : un produit
    scalaire cosinus et un score BM25 ne se somment pas, leurs rangs si.
    """
    fusion: dict[int, float] = defaultdict(float)
    for nom, ordre in listes.items():
        poids_canal = poids.get(nom, 1.0)
        for rang, position in enumerate(ordre):
            fusion[position] += poids_canal / (rrf_k + rang)

    meilleurs = sorted(fusion.items(), key=lambda paire: -paire[1])[:k]
    return [
        Candidat(
            position=position,
            score_fusion=float(score),
            scores=dict(scores_par_canal.get(position, {})),
        )
        for position, score in meilleurs
    ]


def rechercher(
    *,
    elements: list[dict[str, Any]],
    masque: np.ndarray,
    scores_dense: np.ndarray | None = None,
    scores_lexical: np.ndarray | None = None,
    scores_image_texte: np.ndarray | None = None,
    scores_image_image: np.ndarray | None = None,
    poids: dict[str, float],
    rrf_k: int,
    k: int,
) -> list[Candidat]:
    """Classe chaque canal fourni, puis fusionne. Retourne [] si aucun element n'est autorise.

    Une liste vide n'est pas un echec : c'est la reponse correcte quand l'agent n'a acces a aucun
    document sur le sujet. L'appelant s'abstient alors, sans reveler ce qu'il ne peut pas montrer.
    """
    if not masque.any():
        return []

    listes: dict[str, list[int]] = {}
    scores_par_canal: dict[int, dict[str, float]] = defaultdict(dict)

    for nom, scores in (
        ("dense", scores_dense),
        ("lexical", scores_lexical),
        ("image_texte", scores_image_texte),
        ("image_image", scores_image_image),
    ):
        if scores is None:
            continue
        ordre = classer(scores, masque, k)
        if not ordre:
            continue
        listes[nom] = ordre
        for position in ordre:
            scores_par_canal[position][nom] = float(scores[position])

    if not listes:
        return []
    return fusionner(listes, scores_par_canal, poids=poids, rrf_k=rrf_k, k=k)


def scores_visuels(
    vecteur_requete: np.ndarray,
    vecteurs_image: np.ndarray,
    positions_visuelles: list[int],
    nombre_elements: int,
) -> np.ndarray:
    """Replace les similarites visuelles aux positions des elements porteurs d'image.

    Les elements sans image restent a moins l'infini : ils ne peuvent pas etre classes par un
    canal visuel, mais gardent leurs chances sur les canaux dense et lexical.
    """
    scores = np.full(nombre_elements, -np.inf, dtype=np.float64)
    if len(positions_visuelles):
        scores[positions_visuelles] = vecteurs_image @ vecteur_requete
    return scores
