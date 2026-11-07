"""Localisation d'un composant sur une photo : boite englobante rendue par le modele de vision.

Portage de la cellule 31, avec un ecart impose par le deploiement. En Python, le processeur de
Qwen2.5-VL retourne « image_grid_thw », qui donne les dimensions de l'image redimensionnee vue par
le modele. Servi par llama.cpp en HTTP, ce tenseur n'est pas expose. Les coordonnees rendues par
le modele sont pourtant exprimees dans cette image-la, pas dans la photo d'origine : sans le
facteur d'echelle, toutes les boites sont decalees.

La grille est donc recalculee ici en reproduisant « smart_resize », l'algorithme de
redimensionnement de Qwen2.5-VL. C'est une reimplementation, pas une lecture : elle doit etre
calibree contre des boites de reference (scripts/calibrer_localisation.py).

Specification : docs/spec-module-ra.md, section 6.7.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

# Qwen2.5-VL decoupe l'image en patchs de 14 px puis fusionne par blocs de 2 x 2 : les dimensions
# de l'image vue par le modele sont donc des multiples de 28.
TAILLE_PATCH = 14
FUSION = 2
FACTEUR = TAILLE_PATCH * FUSION

# Au-dela de ce rapport largeur/hauteur, Qwen2.5-VL refuse l'image.
RAPPORT_MAX = 200

CONSIGNE = (
    'Locate "{cible}" in the image and output its bbox coordinates in JSON format: '
    '[{{"bbox_2d": [x1, y1, x2, y2], "label": "..."}}]. If it is not visible, output [].'
)

_TABLEAU_JSON = re.compile(r"\[.*\]", re.S)
_VIRGULE_TRAINANTE = re.compile(r",\s*([}\]])")


def smart_resize(
    hauteur: int,
    largeur: int,
    *,
    facteur: int = FACTEUR,
    min_pixels: int,
    max_pixels: int,
) -> tuple[int, int]:
    """Dimensions de l'image telle que Qwen2.5-VL la voit.

    Reproduction de l'algorithme de reference : arrondi au multiple du facteur, puis mise a
    l'echelle si le nombre de pixels sort des bornes. Le rapport d'aspect est preserve.
    """
    if hauteur <= 0 or largeur <= 0:
        raise ValueError(f"dimensions invalides : {largeur}x{hauteur}")
    if max(hauteur, largeur) / min(hauteur, largeur) > RAPPORT_MAX:
        raise ValueError(
            f"rapport d'aspect {max(hauteur, largeur) / min(hauteur, largeur):.1f} "
            f"au-dela de la limite de {RAPPORT_MAX}"
        )

    hauteur_barre = max(facteur, round(hauteur / facteur) * facteur)
    largeur_barre = max(facteur, round(largeur / facteur) * facteur)

    if hauteur_barre * largeur_barre > max_pixels:
        beta = math.sqrt((hauteur * largeur) / max_pixels)
        hauteur_barre = max(facteur, math.floor(hauteur / beta / facteur) * facteur)
        largeur_barre = max(facteur, math.floor(largeur / beta / facteur) * facteur)
    elif hauteur_barre * largeur_barre < min_pixels:
        beta = math.sqrt(min_pixels / (hauteur * largeur))
        hauteur_barre = math.ceil(hauteur * beta / facteur) * facteur
        largeur_barre = math.ceil(largeur * beta / facteur) * facteur

    return hauteur_barre, largeur_barre


def facteurs_echelle(
    largeur_photo: int,
    hauteur_photo: int,
    *,
    min_pixels: int,
    max_pixels: int,
) -> tuple[float, float]:
    """Facteurs (fx, fy) ramenant les coordonnees du modele vers les pixels de la photo."""
    hauteur_modele, largeur_modele = smart_resize(
        hauteur_photo, largeur_photo, min_pixels=min_pixels, max_pixels=max_pixels
    )
    return largeur_photo / largeur_modele, hauteur_photo / hauteur_modele


def extraire_boites(
    brut: str,
    *,
    cible: str,
    largeur_photo: int,
    hauteur_photo: int,
    min_pixels: int,
    max_pixels: int,
) -> list[dict[str, Any]]:
    """Analyse la sortie du modele et ramene les boites aux pixels de la photo d'origine.

    Une sortie inanalysable rend une liste vide : le modele a le droit de ne rien trouver, et un
    JSON malforme ne doit pas devenir une boite fantaisiste dessinee sur la photo du technicien.
    """
    correspondance = _TABLEAU_JSON.search(brut or "")
    if not correspondance:
        return []

    try:
        objets = json.loads(_VIRGULE_TRAINANTE.sub(r"\1", correspondance.group(0)))
    except json.JSONDecodeError:
        return []
    if not isinstance(objets, list):
        return []

    try:
        fx, fy = facteurs_echelle(
            largeur_photo, hauteur_photo, min_pixels=min_pixels, max_pixels=max_pixels
        )
    except ValueError:
        return []

    boites: list[dict[str, Any]] = []
    for objet in objets:
        if not isinstance(objet, dict):
            continue
        coordonnees = objet.get("bbox_2d")
        if not isinstance(coordonnees, (list, tuple)) or len(coordonnees) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in coordonnees)
        except (TypeError, ValueError):
            continue

        # Le modele intervertit parfois les coins ; on remet dans l'ordre avant de borner.
        gauche, droite = sorted((x1 * fx, x2 * fx))
        haut, bas = sorted((y1 * fy, y2 * fy))
        boite = [
            max(0, round(gauche)),
            max(0, round(haut)),
            min(largeur_photo, round(droite)),
            min(hauteur_photo, round(bas)),
        ]
        if boite[2] <= boite[0] or boite[3] <= boite[1]:
            continue  # boite degeneree apres bornage
        boites.append({"label": objet.get("label") or cible, "bbox": boite})

    return boites


def dessiner(image, boites: list[dict[str, Any]]):
    """Trace les boites sur une copie de la photo, en rouge CAMRAIL."""
    from PIL import ImageDraw

    annotee = image.copy()
    dessin = ImageDraw.Draw(annotee)
    epaisseur = max(3, annotee.width // 200)
    for boite in boites:
        dessin.rectangle(boite["bbox"], outline=(196, 30, 38), width=epaisseur)
        dessin.text(
            (boite["bbox"][0] + 4, max(0, boite["bbox"][1] - 14)),
            boite["label"],
            fill=(196, 30, 38),
        )
    return annotee
