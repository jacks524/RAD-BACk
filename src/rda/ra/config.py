"""Parametres du module RA, lus depuis les variables RDA_RA_* et le fichier .env.

Configuration distincte de celle de KALATI : le module a ses propres services d'inference, ses
propres delais et son propre dossier d'artefacts. Rien n'est code en dur.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ParametresRA(BaseSettings):
    """Parametres du module RA."""

    model_config = SettingsConfigDict(env_prefix="RDA_RA_", env_file=".env", extra="ignore")

    actif: bool = True

    # --- services d'inference -------------------------------------------------
    vision_url: str = "http://ra-vision:8080"
    encodeurs_url: str = "http://ra-encodeurs:8082"

    # Une reponse avec image sur CPU prend plusieurs dizaines de secondes : ces delais sont
    # larges a dessein. Un depassement produit une erreur propre, jamais un plantage.
    delai_vision: float = 120.0
    delai_localisation: float = 90.0
    delai_encodeurs: float = 30.0
    delai_sante: float = 3.0

    # --- donnees --------------------------------------------------------------
    artefacts_dir: Path = Path("/ra-data/artefacts")
    depot_dir: Path = Path("/ra-data/uploads")
    minio_bucket: str = "ra-images"

    # --- langue ---------------------------------------------------------------
    # Langue de travail du deploiement. Sert quand la question est trop courte pour qu'on
    # devine la sienne — « couple de serrage » n'a pas assez de mots outils pour trancher.
    langue_preferee: str = "fr"
    # Penalite appliquee au score de reclassement d'un document dans une autre langue. Assez
    # forte pour faire passer devant l'equivalent traduit, assez faible pour ne pas ecarter un
    # document qui n'existe que dans cette langue.
    penalite_autre_langue: float = 2.5
    # Penalite d'un element majoritairement illisible : l'extraction PDF a aplati certains
    # schemas de cablage en suites de caracteres isoles. Ces elements restent utiles a la
    # recherche — les valeurs y figurent — mais ne doivent pas etre restitues tels quels.
    penalite_illisible: float = 3.0
    seuil_lisibilite: float = 0.5

    # --- photos ---------------------------------------------------------------
    taille_max_photo_mo: int = 10
    types_mime_photo: str = "image/jpeg,image/png,image/webp"
    max_cote_photo: int = 1600

    # --- comptes de test ------------------------------------------------------
    mdp_technicien_dmat: str = Field(default="")
    mdp_technicien_dif: str = Field(default="")
    mdp_securite: str = Field(default="")

    @computed_field
    @property
    def taille_max_photo_octets(self) -> int:
        return self.taille_max_photo_mo * 1024 * 1024

    @computed_field
    @property
    def liste_types_mime_photo(self) -> list[str]:
        return [t.strip() for t in self.types_mime_photo.split(",") if t.strip()]


@lru_cache
def obtenir_parametres_ra() -> ParametresRA:
    """Retourne les parametres RA mis en cache."""

    return ParametresRA()
