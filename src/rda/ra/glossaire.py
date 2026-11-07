"""Enrichissement de la requete par le glossaire metier bilingue.

Portage fidele de la cellule 15. La question enrichie alimente les canaux dense et lexical ; le
canal image_texte recoit la question brute, SigLIP2 n'ayant pas ete entraine sur ces synonymes.
"""

from __future__ import annotations

from rda.ra.lexical import sans_accents

LONGUEUR_MIN_SYNONYME = 2


def enrichir_requete(question: str, glossaire: dict[str, list[str]]) -> str:
    """Ajoute les equivalents (FR/EN, abreviations) des termes metier detectes.

    La correspondance joue dans les deux sens : un terme canonique present fait ajouter ses
    synonymes, et un synonyme present fait ajouter le terme canonique.
    """
    question_normalisee = sans_accents(question.lower())
    ajouts: list[str] = []
    for terme, synonymes in glossaire.items():
        if sans_accents(terme.lower()) in question_normalisee:
            ajouts.extend(synonymes)
            continue
        for synonyme in synonymes:
            if (
                len(synonyme) > LONGUEUR_MIN_SYNONYME
                and sans_accents(synonyme.lower()) in question_normalisee
            ):
                ajouts.append(terme)
                break
    if not ajouts:
        return question
    # dict.fromkeys : doublons retires en conservant l'ordre d'apparition.
    return question + " " + " ".join(dict.fromkeys(ajouts))
