"""Service d'inference CPU du module RA : encodeur texte, encodeur visuel et reclasseur.

Isole toute la charge torch hors du conteneur API. Les trois modeles sont charges une fois au
demarrage ; l'API ne dialogue avec eux que par HTTP.

Espaces vectoriels distincts, jamais interchangeables :
  - /encoder/texte         e5, 768 dims  -- canal dense, index texte
  - /encoder/visuel-texte  SigLIP2, 768  -- canal image_texte (question -> images)
  - /encoder/visuel-image  SigLIP2, 768  -- canal image_image et identification
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

import numpy as np
import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
journal = logging.getLogger("ra-encodeurs")

MODELE_TEXTE = os.getenv("RA_MODELE_TEXTE", "intfloat/multilingual-e5-base")
MODELE_VISUEL = os.getenv("RA_MODELE_VISUEL", "google/siglip2-base-patch16-384")
MODELE_RECLASSEUR = os.getenv(
    "RA_MODELE_RECLASSEUR", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
)

LOT_TEXTE = int(os.getenv("RA_LOT_TEXTE", "32"))
LOT_IMAGE = int(os.getenv("RA_LOT_IMAGE", "16"))
LOT_RECLASSEUR = int(os.getenv("RA_LOT_RECLASSEUR", "16"))

# Le notebook tronque a 1500 caracteres avant reclassement (cellule 27) ; on garde la meme borne
# pour que les scores de confiance soient comparables a ceux de la campagne d'evaluation.
MAX_CARACTERES_RECLASSEUR = 1500

MODELES: dict[str, object] = {}


# --------------------------------------------------------------------------- schemas


class DemandeTexte(BaseModel):
    """Le prefixe e5 est obligatoire et explicite : « passage » pour indexer, « query » pour
    interroger. Un index construit avec un prefixe et interroge avec l'autre donne des scores
    silencieusement faux, d'ou l'absence de valeur par defaut."""

    textes: list[str] = Field(min_length=1)
    prefixe: Literal["passage", "query"]


class DemandeVisuelTexte(BaseModel):
    textes: list[str] = Field(min_length=1)


class DemandeVisuelImage(BaseModel):
    images_base64: list[str] = Field(min_length=1)


class DemandeReclassement(BaseModel):
    question: str
    textes: list[str] = Field(min_length=1)


class ReponseVecteurs(BaseModel):
    vecteurs: list[list[float]]
    modele: str
    dimensions: int


class ReponseScores(BaseModel):
    scores: list[float]
    modele: str


# --------------------------------------------------------------------------- utilitaires


def _decoder_image(donnees_base64: str) -> Image.Image:
    """Decode une image base64, corrige l'orientation EXIF, convertit en RGB.

    L'API redresse deja les photos avant de les transmettre ; on le refait ici pour qu'un appel
    direct au service ne puisse pas produire un vecteur calcule sur une image couchee.
    """
    try:
        brut = base64.b64decode(donnees_base64, validate=True)
    except (binascii.Error, ValueError) as erreur:
        raise ValueError(f"image base64 invalide : {erreur}") from erreur
    try:
        image = Image.open(io.BytesIO(brut))
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as erreur:
        raise ValueError(f"image illisible : {erreur}") from erreur
    return image.convert("RGB") if image.mode != "RGB" else image


def _normaliser(vecteurs: torch.Tensor) -> np.ndarray:
    return torch.nn.functional.normalize(vecteurs.float(), dim=-1).cpu().numpy()


# --------------------------------------------------------------------------- cycle de vie


@asynccontextmanager
async def duree_vie(_: FastAPI):
    from sentence_transformers import CrossEncoder, SentenceTransformer
    from transformers import AutoModel, AutoProcessor

    torch.set_grad_enabled(False)
    torch.set_num_threads(int(os.getenv("RA_THREADS_TORCH", "4")))

    journal.info("chargement de l'encodeur texte %s", MODELE_TEXTE)
    MODELES["texte"] = SentenceTransformer(MODELE_TEXTE, device="cpu")

    journal.info("chargement de l'encodeur visuel %s", MODELE_VISUEL)
    MODELES["visuel"] = AutoModel.from_pretrained(MODELE_VISUEL, torch_dtype=torch.float32).eval()
    MODELES["processeur_visuel"] = AutoProcessor.from_pretrained(MODELE_VISUEL)

    journal.info("chargement du reclasseur %s", MODELE_RECLASSEUR)
    MODELES["reclasseur"] = CrossEncoder(MODELE_RECLASSEUR, max_length=512, device="cpu")

    journal.info("les trois modeles sont charges")
    yield
    MODELES.clear()


application = FastAPI(title="RA encodeurs", version="0.1.0", lifespan=duree_vie)


@application.exception_handler(ValueError)
async def _gerer_valeur(_, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": "ENTREE_INVALIDE", "message": str(exc)})


# --------------------------------------------------------------------------- routes


@application.get("/sante")
async def sante() -> dict:
    charges = sorted(k for k in MODELES if not k.startswith("processeur"))
    return {
        "statut": "OK" if len(charges) == 3 else "DEGRADE",
        "modeles": {
            "texte": MODELE_TEXTE,
            "visuel": MODELE_VISUEL,
            "reclasseur": MODELE_RECLASSEUR,
        },
        "charges": charges,
    }


@application.post("/encoder/texte", response_model=ReponseVecteurs)
async def encoder_texte(demande: DemandeTexte) -> ReponseVecteurs:
    """Encode des textes avec e5. Portage de la cellule 22 (index) et 25 (requete)."""
    modele = MODELES["texte"]
    entrees = [f"{demande.prefixe}: {t}" for t in demande.textes]
    vecteurs = modele.encode(
        entrees,
        batch_size=LOT_TEXTE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return ReponseVecteurs(
        vecteurs=vecteurs.tolist(), modele=MODELE_TEXTE, dimensions=int(vecteurs.shape[1])
    )


@application.post("/encoder/visuel-texte", response_model=ReponseVecteurs)
async def encoder_visuel_texte(demande: DemandeVisuelTexte) -> ReponseVecteurs:
    """Projette un texte dans l'espace SigLIP2. Portage de siglip_textes (cellule 23)."""
    modele, processeur = MODELES["visuel"], MODELES["processeur_visuel"]
    entrees = processeur(
        text=demande.textes,
        padding="max_length",
        max_length=64,
        truncation=True,
        return_tensors="pt",
    )
    vecteurs = _normaliser(modele.get_text_features(**entrees))
    return ReponseVecteurs(
        vecteurs=vecteurs.tolist(), modele=MODELE_VISUEL, dimensions=int(vecteurs.shape[1])
    )


@application.post("/encoder/visuel-image", response_model=ReponseVecteurs)
async def encoder_visuel_image(demande: DemandeVisuelImage) -> ReponseVecteurs:
    """Encode des images dans l'espace SigLIP2. Portage de siglip_images (cellule 23)."""
    modele, processeur = MODELES["visuel"], MODELES["processeur_visuel"]
    images = [_decoder_image(d) for d in demande.images_base64]
    sorties = []
    for debut in range(0, len(images), LOT_IMAGE):
        entrees = processeur(images=images[debut : debut + LOT_IMAGE], return_tensors="pt")
        sorties.append(_normaliser(modele.get_image_features(**entrees)))
    vecteurs = np.concatenate(sorties)
    return ReponseVecteurs(
        vecteurs=vecteurs.tolist(), modele=MODELE_VISUEL, dimensions=int(vecteurs.shape[1])
    )


@application.post("/reclasser", response_model=ReponseScores)
async def reclasser(demande: DemandeReclassement) -> ReponseScores:
    """Note les paires (question, texte). Scores bruts : la calibration reste cote API (cellule 27)."""
    paires = [(demande.question, t[:MAX_CARACTERES_RECLASSEUR]) for t in demande.textes]
    scores = MODELES["reclasseur"].predict(
        paires, batch_size=LOT_RECLASSEUR, show_progress_bar=False
    )
    return ReponseScores(scores=[float(s) for s in scores], modele=MODELE_RECLASSEUR)
