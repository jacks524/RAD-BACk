"""Schemas d'entree et de sortie des routes /ra/*.

Ces schemas sont le contrat que consomme l'application de test : tout changement ici se repercute
sur le front. Les champs sont nommes comme dans le notebook, pour qu'une trace d'execution et une
reponse d'API se lisent de la meme facon.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ModeReponse = Literal[
    "EXTRACTIF", "GENERATIF", "ABSTENTION", "NEUTRALISATION", "CONVERSATION", "DESCRIPTION"
]


class Citation(BaseModel):
    """Une source restituee. Le rang est le numero cite entre crochets dans la reponse."""

    rang: int
    id: str
    type: str
    reference: str
    titre_doc: str
    indice: str | None = None
    page: int | None = None
    image: str | None = Field(
        default=None, description="Chemin relatif, a demander via GET /ra/images/{chemin}"
    )
    extrait: str = Field(
        default="", description="Ce que dit cette source, nettoyé et recentré sur la question"
    )
    score_dense: float | None = None
    score_lexical: float | None = None
    score_image_texte: float | None = None
    score_image_image: float | None = None


class Identification(BaseModel):
    """Resultat d'une reconnaissance d'equipement par photo."""

    confiant: bool
    equipement_id: str | None = None
    equipement_nom: str | None = None
    score: float | None = None
    ecart_second: float | None = None
    votes: dict[str, float] | None = None
    raison: str | None = None


class Boite(BaseModel):
    """Boite englobante, en pixels de la photo d'origine."""

    label: str
    bbox: list[int] = Field(min_length=4, max_length=4, description="[x1, y1, x2, y2]")


class ReponseRA(BaseModel):
    """Reponse a une question, citee ou abstenue."""

    mode: ModeReponse
    reponse: str
    confiance: float
    seuil: float | None = None
    perimetre: str | None = None
    equipement: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    identification: Identification | None = None
    # Langue de la reponse : celle de la question, jamais celle du document.
    langue: str = Field(default="fr", description="Langue des messages du système")
    # Averti quand l'extrait cite vient d'un manuel dans une autre langue.
    mention_source: str | None = None
    # Reperage sur la photo du technicien, quand la question en demandait un.
    cible: str | None = Field(
        default=None, description="Composant que la question demandait de situer"
    )
    boites: list[Boite] = Field(default_factory=list)
    image_annotee: str | None = Field(
        default=None, description="Reference de la photo annotee, a demander via GET /ra/images"
    )
    latence_s: float


class ReponseLocalisation(BaseModel):
    cible: str
    boites: list[Boite] = Field(default_factory=list)
    largeur_photo: int
    hauteur_photo: int
    image_annotee: str | None = Field(
        default=None, description="Reference de l'image annotee, a demander via GET /ra/images"
    )
    latence_s: float


class EquipementSortie(BaseModel):
    id: str
    nom: str
    direction: str
    famille: str
    groupe: str
    constructeur: str | None = None
    modele: str | None = None
    nb_elements: int = 0
    nb_documents: int = 0
    nb_images: int = 0


class DocumentSortie(BaseModel):
    cle_doc: str
    titre_doc: str
    type_doc: str
    indice: str | None = None
    date_effet: str | None = None
    date_abrogation: str | None = None
    nb_elements: int
    nb_images: int
    page_min: int | None = None
    page_max: int | None = None


class PhotoVersee(BaseModel):
    id_photo: str
    equipement_id: str | None = None
    ref_objet: str
    largeur: int
    hauteur: int
    taille_octets: int


class EntreeJournalRA(BaseModel):
    id_entree: str
    horodatage: str
    ref_agent: str | None = None
    action: str
    equipement_id: str | None = None
    mode: str | None = None
    confiance: float | None = None
    seuil_applique: float | None = None
    nb_citations: int | None = None
    latence_ms: int | None = None
    resultat: str


class SanteRA(BaseModel):
    """Etat du module, expose par GET /health."""

    actif: bool
    artefacts_charges: bool
    nb_elements: int = 0
    nb_visuels: int = 0
    nb_equipements: int = 0
    version_artefacts: str | None = None
    encodeur_texte: str | None = None
    politique_version: int | None = None
    ra_vision: dict[str, Any] = Field(default_factory=dict)
    ra_encodeurs: dict[str, Any] = Field(default_factory=dict)
