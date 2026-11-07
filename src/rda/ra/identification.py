"""Identification d'equipement a partir d'une photo.

Portage fidele de la cellule 29 du notebook : vote pondere des cinq visuels les plus proches,
puis double condition de seuil et de marge.

La marge est ce qui distingue une reconnaissance d'une devinette. Un score eleve sur deux
equipements a la fois ne prouve rien — c'est le cas des photos de detail, un roulement se
ressemblant d'une machine a l'autre. Sans marge, le systeme trancherait au hasard.

Specification : docs/spec-module-ra.md, section 6.6.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import numpy as np

NB_VOTANTS = 5


def identifier(
    vecteur_photo: np.ndarray,
    *,
    vecteurs_image: np.ndarray,
    positions_visuelles: list[int],
    elements: list[dict[str, Any]],
    equipements: dict[str, dict[str, Any]],
    seuil: float,
    marge: float,
    groupes: Iterable[str] | None = None,
    exclure: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Retourne l'equipement le plus probable pour une photo.

    « exclure » ignore des chemins d'image : sert a l'evaluation en leave-one-out, ou chaque photo
    doit etre identifiee sans elle-meme dans l'index.
    """
    if not len(positions_visuelles):
        return {"confiant": False, "raison": "aucun visuel indexé"}

    similarites = vecteurs_image @ vecteur_photo
    groupes_autorises = None if groupes is None else set(groupes)
    chemins_exclus = set(exclure or ())

    candidats: list[tuple[float, int]] = []
    for rang, position in enumerate(positions_visuelles):
        element = elements[position]
        if groupes_autorises is not None and element["groupe"] not in groupes_autorises:
            continue
        if element["chemin_image"] in chemins_exclus:
            continue
        candidats.append((float(similarites[rang]), position))

    if not candidats:
        return {"confiant": False, "raison": "aucun visuel autorisé"}

    candidats.sort(reverse=True)
    votants = candidats[:NB_VOTANTS]

    votes: dict[str, float] = defaultdict(float)
    for similarite, position in votants:
        votes[elements[position]["equipement_id"]] += similarite

    classement = sorted(votes.items(), key=lambda paire: -paire[1])
    gagnant = classement[0][0]

    score = max(s for s, p in votants if elements[p]["equipement_id"] == gagnant)
    second = max(
        (s for s, p in votants if elements[p]["equipement_id"] != gagnant),
        default=0.0,
    )

    return {
        "confiant": score >= seuil and (score - second) >= marge,
        "equipement_id": gagnant,
        "equipement_nom": equipements.get(gagnant, {}).get("nom", gagnant),
        "score": round(score, 3),
        "ecart_second": round(score - second, 3),
        "votes": {nom: round(valeur, 3) for nom, valeur in classement},
    }
