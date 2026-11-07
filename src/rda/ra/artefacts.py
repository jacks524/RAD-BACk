"""Contrat des artefacts du module RA : lecture et controles d'integrite.

Le contrat est celui de la cellule 46 du notebook, verifie contre les fichiers reels. Aucune
colonne n'est facultative et aucun champ n'est invente : un artefact incomplet est refuse, jamais
complete par defaut. Un index silencieusement faux coute plus cher qu'un chargement qui echoue.

Specification : docs/spec-module-ra.md, section 3.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

DIMENSIONS = 768

# Les 21 colonnes de elements.parquet, dans l'ordre du contrat (notebook, cellule 46).
COLONNES_ELEMENTS: tuple[str, ...] = (
    "id",
    "equipement_id",
    "equipement_nom",
    "famille",
    "direction",
    "groupe",
    "cle_doc",
    "titre_doc",
    "type_doc",
    "indice",
    "date_effet",
    "date_abrogation",
    "chemin_hierarchique",
    "page_debut",
    "page_fin",
    "type",
    "texte",
    "reference",
    "texte_ocr",
    "chemin_image",
    "description_json",
)

FICHIERS_REQUIS: tuple[str, ...] = (
    "elements.parquet",
    "embeddings_texte.npy",
    "embeddings_image.npy",
    "index_visuel.json",
    "equipements.json",
    "glossaire.json",
    "politique.json",
    "modeles.json",
)

# Tolerance sur la norme des plongements : ils sont exportes normalises.
NORME_MIN, NORME_MAX = 0.99, 1.01


class ArtefactInvalide(Exception):
    """Un controle du contrat a echoue. Le message nomme le controle et ce qui a ete observe."""


@dataclass(frozen=True)
class Artefacts:
    """Artefacts charges et valides."""

    dossier: Path
    elements: list[dict[str, Any]]
    vecteurs_texte: np.ndarray
    vecteurs_image: np.ndarray
    index_visuel: list[str]
    equipements: list[dict[str, Any]]
    glossaire: dict[str, list[str]]
    politique: dict[str, Any]
    modeles: dict[str, Any]
    empreinte: str

    @property
    def positions_visuelles(self) -> list[int]:
        """Positions, dans « elements », des elements portant une image — l'equivalent de VIS_IDX."""
        rang = {e["id"]: i for i, e in enumerate(self.elements)}
        return [rang[identifiant] for identifiant in self.index_visuel]


def _lire_json(chemin: Path) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erreur:
        raise ArtefactInvalide(f"{chemin.name} : JSON illisible — {erreur}") from erreur


def _empreinte_dossier(dossier: Path) -> str:
    """Empreinte stable des fichiers du contrat, pour tracer ce qui a ete charge."""
    condensat = hashlib.sha256()
    for nom in sorted(FICHIERS_REQUIS):
        condensat.update(nom.encode("utf-8"))
        condensat.update((dossier / nom).read_bytes())
    return condensat.hexdigest()


def charger(dossier: Path) -> Artefacts:
    """Lit les artefacts et applique les six controles du contrat.

    Leve ArtefactInvalide des le premier controle en echec, en nommant ce qui a ete observe.
    """
    import pandas as pd

    dossier = Path(dossier)
    if not dossier.is_dir():
        raise ArtefactInvalide(f"dossier d'artefacts introuvable : {dossier}")

    manquants = [nom for nom in FICHIERS_REQUIS if not (dossier / nom).is_file()]
    if manquants:
        raise ArtefactInvalide("fichiers absents du dossier d'artefacts : " + ", ".join(manquants))

    cadre = pd.read_parquet(dossier / "elements.parquet")
    colonnes_absentes = [c for c in COLONNES_ELEMENTS if c not in cadre.columns]
    if colonnes_absentes:
        raise ArtefactInvalide(
            "colonnes absentes de elements.parquet : " + ", ".join(colonnes_absentes)
        )

    elements = [
        {colonne: _valeur_python(ligne[colonne]) for colonne in COLONNES_ELEMENTS}
        for _, ligne in cadre.iterrows()
    ]

    vecteurs_texte = np.load(dossier / "embeddings_texte.npy")
    vecteurs_image = np.load(dossier / "embeddings_image.npy")
    index_visuel = _lire_json(dossier / "index_visuel.json")
    equipements = _lire_json(dossier / "equipements.json")
    glossaire = _lire_json(dossier / "glossaire.json")
    politique = _lire_json(dossier / "politique.json")
    modeles = _lire_json(dossier / "modeles.json")

    _verifier(elements, vecteurs_texte, vecteurs_image, index_visuel, modeles, dossier)

    return Artefacts(
        dossier=dossier,
        elements=elements,
        vecteurs_texte=vecteurs_texte,
        vecteurs_image=vecteurs_image,
        index_visuel=index_visuel,
        equipements=equipements,
        glossaire=glossaire,
        politique=politique,
        modeles=modeles,
        empreinte=_empreinte_dossier(dossier),
    )


def _valeur_python(valeur: Any) -> Any:
    """Convertit les types pandas/numpy en types Python simples, en preservant les valeurs nulles."""
    import pandas as pd

    if valeur is None or (not isinstance(valeur, (list, dict, np.ndarray)) and pd.isna(valeur)):
        return None
    if isinstance(valeur, np.generic):
        return valeur.item()
    return valeur


def _verifier(
    elements: list[dict[str, Any]],
    vecteurs_texte: np.ndarray,
    vecteurs_image: np.ndarray,
    index_visuel: list[str],
    modeles: dict[str, Any],
    dossier: Path,
) -> None:
    """Les six controles de la section 3.2 de la specification."""

    # 1. un vecteur texte par element
    if vecteurs_texte.shape != (len(elements), DIMENSIONS):
        raise ArtefactInvalide(
            f"embeddings_texte.npy a la forme {vecteurs_texte.shape}, "
            f"attendu ({len(elements)}, {DIMENSIONS})"
        )

    # 2. un vecteur image par entree de l'index visuel
    if vecteurs_image.shape != (len(index_visuel), DIMENSIONS):
        raise ArtefactInvalide(
            f"embeddings_image.npy a la forme {vecteurs_image.shape}, "
            f"attendu ({len(index_visuel)}, {DIMENSIONS})"
        )

    # 3. tout identifiant de l'index visuel existe et porte bien une image
    par_identifiant = {e["id"]: e for e in elements}
    if len(par_identifiant) != len(elements):
        raise ArtefactInvalide("elements.parquet contient des identifiants en double")
    inconnus = [i for i in index_visuel if i not in par_identifiant]
    if inconnus:
        raise ArtefactInvalide(
            f"{len(inconnus)} identifiants d'index_visuel absents de elements.parquet, "
            f"dont : {', '.join(inconnus[:3])}"
        )
    sans_image = [i for i in index_visuel if not par_identifiant[i]["chemin_image"]]
    if sans_image:
        raise ArtefactInvalide(
            f"{len(sans_image)} elements de l'index visuel n'ont pas de chemin_image, "
            f"dont : {', '.join(sans_image[:3])}"
        )

    # 4. toute image referencee existe sur le disque
    absentes = [
        element["chemin_image"]
        for element in elements
        if element["chemin_image"] and not (dossier / element["chemin_image"]).is_file()
    ]
    if absentes:
        raise ArtefactInvalide(
            f"{len(absentes)} images referencees sont absentes du dossier, "
            f"dont : {', '.join(absentes[:3])}"
        )

    # 5. les plongements sont normalises
    for nom, vecteurs in (("texte", vecteurs_texte), ("image", vecteurs_image)):
        if not len(vecteurs):
            continue
        normes = np.linalg.norm(vecteurs, axis=1)
        if not np.all((normes > NORME_MIN) & (normes < NORME_MAX)):
            raise ArtefactInvalide(
                f"plongements {nom} non normalises : norme observee entre "
                f"{normes.min():.4f} et {normes.max():.4f}"
            )

    # 6. les dimensions declarees correspondent
    for cle in ("dimensions_texte", "dimensions_image"):
        declaree = modeles.get(cle)
        if declaree is not None and int(declaree) != DIMENSIONS:
            raise ArtefactInvalide(
                f"modeles.json declare {cle} = {declaree}, attendu {DIMENSIONS}"
            )
