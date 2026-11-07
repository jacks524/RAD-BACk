"""Normalisation des photos versees par les techniciens.

Les photos Android arrivent presque toujours en JPEG avec une orientation EXIF : le capteur ecrit
l'image dans son orientation native et note la rotation a appliquer dans une etiquette. Une
bibliotheque qui ignore cette etiquette encode une photo prise en portrait couchee sur le cote.
La similarite visuelle s'effondre alors, et le modele de vision decrit une scene pivotee de 90
degres. Le redressement est donc fait avant tout autre traitement, sans exception.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from rda.commun.erreurs import ErreurRDA
from rda.ra.config import obtenir_parametres_ra


class PhotoInvalide(ErreurRDA):
    """La photo transmise est inexploitable : trop lourde, format refuse, ou illisible."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(
            code="RA_PHOTO_INVALIDE", message=message, detail=detail or {}, statut=400
        )


def verifier_photo(donnees: bytes, type_mime: str | None) -> None:
    """Controle la taille et le type declare avant tout decodage."""
    parametres = obtenir_parametres_ra()

    if not donnees:
        raise PhotoInvalide("La photo transmise est vide.")

    if len(donnees) > parametres.taille_max_photo_octets:
        raise PhotoInvalide(
            f"La photo depasse {parametres.taille_max_photo_mo} Mo.",
            {"taille_octets": len(donnees), "maximum": parametres.taille_max_photo_octets},
        )

    types_admis = parametres.liste_types_mime_photo
    if type_mime and type_mime.split(";")[0].strip().lower() not in types_admis:
        raise PhotoInvalide(
            "Format d'image non pris en charge.",
            {"type_recu": type_mime, "types_admis": types_admis},
        )


def normaliser(donnees: bytes, max_cote: int | None = None) -> Image.Image:
    """Redresse selon l'EXIF, convertit en RGB, reduit le grand cote."""
    try:
        image = Image.open(io.BytesIO(donnees))
        image.load()
    except (UnidentifiedImageError, OSError) as erreur:
        raise PhotoInvalide("Image illisible ou corrompue.", {"cause": str(erreur)}) from erreur

    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")

    cote = max_cote if max_cote is not None else obtenir_parametres_ra().max_cote_photo
    if cote and max(image.size) > cote:
        image.thumbnail((cote, cote), Image.LANCZOS)
    return image


def en_octets(image: Image.Image, qualite: int = 90) -> bytes:
    """Serialise en JPEG, pour transmission aux services d'inference ou stockage."""
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=qualite)
    return tampon.getvalue()


def preparer(donnees: bytes, type_mime: str | None = None) -> tuple[Image.Image, bytes]:
    """Controle puis normalise. Retourne l'image et sa version JPEG redressee."""
    verifier_photo(donnees, type_mime)
    image = normaliser(donnees)
    return image, en_octets(image)
