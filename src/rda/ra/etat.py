"""Etat en memoire du module RA : matrices de plongements et index lexical.

L'index BM25 n'est pas stockable en base : il est reconstruit au demarrage et apres chaque
chargement d'artefacts. Le cout est negligeable (0,14 s pour 599 elements) et l'ordre des elements
doit correspondre exactement a celui des matrices de plongements, sans quoi les scores designent
les mauvais documents.

L'etat est charge une fois et lu ensuite : aucune route ne le modifie.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from rda.ra.artefacts import Artefacts, charger
from rda.ra.lexical import IndexLexical
from rda.ra.lisibilite import langue_probable

journal = logging.getLogger("rda.ra")


class EtatRA:
    """Index du module, pret a interroger."""

    def __init__(self) -> None:
        self.artefacts: Artefacts | None = None
        self.index_lexical: IndexLexical | None = None
        self.positions_visuelles: list[int] = []
        self.equipements: dict[str, dict[str, Any]] = {}
        self.encodeur_texte: str | None = None
        self.langue_document: dict[str, str] = {}

    @property
    def charge(self) -> bool:
        return self.artefacts is not None

    @property
    def elements(self) -> list[dict[str, Any]]:
        return self.artefacts.elements if self.artefacts else []

    @property
    def politique(self) -> dict[str, Any]:
        return self.artefacts.politique if self.artefacts else {}

    @property
    def glossaire(self) -> dict[str, list[str]]:
        return self.artefacts.glossaire if self.artefacts else {}

    @property
    def vecteurs_texte(self) -> np.ndarray:
        return self.artefacts.vecteurs_texte if self.artefacts else np.zeros((0, 768))

    @property
    def vecteurs_image(self) -> np.ndarray:
        return self.artefacts.vecteurs_image if self.artefacts else np.zeros((0, 768))

    @property
    def dossier(self) -> Path | None:
        return self.artefacts.dossier if self.artefacts else None

    def construire(self, artefacts: Artefacts) -> None:
        """Installe les artefacts et reconstruit l'index lexical."""
        self.artefacts = artefacts
        self.index_lexical = IndexLexical([e["texte"] for e in artefacts.elements])
        self.positions_visuelles = artefacts.positions_visuelles
        self.equipements = {e["id"]: e for e in artefacts.equipements}
        self.encodeur_texte = artefacts.modeles.get("encodeur_texte")
        self.langue_document = _langues_par_document(artefacts.elements)
        journal.info(
            "langues des documents : %s", self.langue_document
        )
        journal.info(
            "module RA : %d elements, %d visuels, %d equipements, index lexical reconstruit",
            len(artefacts.elements),
            len(self.positions_visuelles),
            len(self.equipements),
        )

    def charger_depuis(self, dossier: Path) -> None:
        """Lit les artefacts du dossier et reconstruit l'etat."""
        self.construire(charger(dossier))

    def equipements_visibles(self, groupes: list[str]) -> list[dict[str, Any]]:
        """Referentiel filtre par habilitation, avec les compteurs par equipement."""
        autorises = set(groupes)
        visibles = []
        for identifiant, equipement in self.equipements.items():
            if equipement.get("groupe") not in autorises:
                continue
            concernes = [e for e in self.elements if e["equipement_id"] == identifiant]
            visibles.append(
                {
                    **equipement,
                    "nb_elements": len(concernes),
                    "nb_documents": len({e["cle_doc"] for e in concernes}),
                    "nb_images": sum(1 for e in concernes if e["chemin_image"]),
                }
            )
        return visibles

    def element_par_image(self, chemin_image: str) -> dict[str, Any] | None:
        """Retrouve l'element qui porte cette image, pour en controler l'habilitation."""
        for element in self.elements:
            if element["chemin_image"] == chemin_image:
                return element
        return None


etat_ra = EtatRA()


def _langues_par_document(elements: list[dict[str, Any]]) -> dict[str, str]:
    """Langue de chaque document, par vote majoritaire sur ses elements.

    Element par element, la detection est bruitee : un tableau de valeurs ou une legende de figure
    ne contiennent presque pas de mots outils. Au niveau du document, le vote est net — le corpus
    livre contient le meme manuel constructeur en anglais et en francais, et il faut savoir lequel
    est lequel pour ne pas citer l'anglais a un technicien francophone.
    """
    from collections import Counter

    votes: dict[str, Counter] = {}
    for element in elements:
        langue = langue_probable(element.get("texte") or "")
        if langue:
            votes.setdefault(element["cle_doc"], Counter())[langue] += 1
    return {cle: compte.most_common(1)[0][0] for cle, compte in votes.items() if compte}
