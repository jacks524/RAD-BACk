#!/usr/bin/env python3
"""Calibre la reconstruction de la grille de vision utilisee par la localisation.

    python scripts/calibrer_localisation.py --auto
    python scripts/calibrer_localisation.py --image photo.jpg --cible "roulement"

Pourquoi ce script existe. En Python, le processeur de Qwen2.5-VL retourne « image_grid_thw » :
les dimensions exactes de l'image que le modele a vue. Servi par llama.cpp en HTTP, ce tenseur
n'est pas expose, et « smart_resize » a du etre reimplemente cote API. Une reimplementation qui
derive ne produit pas d'erreur : elle produit des boites decalees, dessinees avec aplomb sur la
photo du technicien. Il faut donc la verifier.

Deux modes :

  --auto   verifie les proprietes qui ne dependent d'aucun modele : multiples de 28, bornes de
           pixels respectees, rapport d'aspect preserve, coherence des facteurs d'echelle. Rapide,
           aucun service requis.
  --image  envoie une vraie photo a ra-vision et rapporte les boites obtenues, a comparer a l'oeil
           ou a une boite de reference fournie par --attendu.

Specification : docs/spec-module-ra.md, section 6.7.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rda.ra.clients import ClientVision, ServiceIndisponible  # noqa: E402
from rda.ra.images import en_octets, normaliser  # noqa: E402
from rda.ra.localisation import (  # noqa: E402
    CONSIGNE,
    FACTEUR,
    extraire_boites,
    facteurs_echelle,
    smart_resize,
)

MIN_PIXELS = 256 * 28 * 28
MAX_PIXELS = 1024 * 28 * 28

# Formats courants, dont ceux des capteurs de telephone en portrait et en paysage.
FORMATS = [
    (640, 480), (800, 600), (1024, 768), (1280, 960), (1600, 1200),
    (1920, 1080), (1080, 1920), (3000, 4000), (4000, 3000),
    (1600, 900), (900, 1600), (512, 512), (2048, 1536),
]


def _dire(message: str = "") -> None:
    print(message, flush=True)


def calibrer_hors_ligne() -> int:
    """Verifie les invariants de smart_resize sur une batterie de formats."""
    _dire(f"{'photo':>12}   {'vue par le modèle':>18}   {'pixels':>9}   {'fx':>6}   {'fy':>6}   écart")
    _dire("-" * 76)

    anomalies = 0
    for largeur, hauteur in FORMATS:
        hauteur_modele, largeur_modele = smart_resize(
            hauteur, largeur, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS
        )
        fx, fy = facteurs_echelle(
            largeur, hauteur, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS
        )
        pixels = hauteur_modele * largeur_modele
        ecart_relatif = abs(fx - fy) / max(fx, fy)

        problemes = []
        if hauteur_modele % FACTEUR or largeur_modele % FACTEUR:
            problemes.append(f"non multiple de {FACTEUR}")
        if pixels > MAX_PIXELS:
            problemes.append("au-dessus du plafond")
        if pixels < MIN_PIXELS:
            problemes.append("sous le plancher")
        if ecart_relatif > 0.05:
            problemes.append(f"fx et fy divergent de {ecart_relatif:.1%}")

        marque = "  ".join(problemes) if problemes else "ok"
        anomalies += bool(problemes)
        _dire(
            f"{largeur:5d}x{hauteur:<5d}   {largeur_modele:8d}x{hauteur_modele:<8d}   "
            f"{pixels:9d}   {fx:6.3f}   {fy:6.3f}   {marque}"
        )

    _dire()
    # Verification de bout en bout : une boite pleine cadre dans l'espace du modele doit revenir
    # aux dimensions exactes de la photo.
    _dire("aller-retour d'une boîte pleine cadre :")
    erreurs_aller_retour = 0
    for largeur, hauteur in FORMATS:
        hauteur_modele, largeur_modele = smart_resize(
            hauteur, largeur, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS
        )
        boites = extraire_boites(
            f'[{{"bbox_2d": [0, 0, {largeur_modele}, {hauteur_modele}], "label": "cadre"}}]',
            cible="cadre",
            largeur_photo=largeur,
            hauteur_photo=hauteur,
            min_pixels=MIN_PIXELS,
            max_pixels=MAX_PIXELS,
        )
        if not boites:
            _dire(f"  {largeur}x{hauteur} : aucune boîte — ANOMALIE")
            erreurs_aller_retour += 1
            continue
        _, _, x2, y2 = boites[0]["bbox"]
        derive = max(abs(x2 - largeur), abs(y2 - hauteur))
        if derive > 2:
            _dire(f"  {largeur}x{hauteur} : dérive de {derive} px — ANOMALIE")
            erreurs_aller_retour += 1

    if erreurs_aller_retour == 0:
        _dire(f"  {len(FORMATS)} formats : dérive au plus 2 px, conforme")

    total = anomalies + erreurs_aller_retour
    _dire()
    _dire("CALIBRATION CONFORME" if total == 0 else f"{total} ANOMALIE(S) — boîtes non fiables")
    return 0 if total == 0 else 1


async def calibrer_en_ligne(arguments: argparse.Namespace) -> int:
    """Envoie une vraie photo au modele et rapporte les boites obtenues."""
    image = normaliser(arguments.image.read_bytes())
    jpeg = en_octets(image)
    _dire(f"photo : {image.width}x{image.height} · cible « {arguments.cible} »")

    hauteur_modele, largeur_modele = smart_resize(
        image.height, image.width, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS
    )
    _dire(f"vue par le modèle : {largeur_modele}x{hauteur_modele}")

    vision = ClientVision(arguments.url_vision)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": ClientVision.image_en_url(jpeg)}},
                {"type": "text", "text": CONSIGNE.format(cible=arguments.cible)},
            ],
        }
    ]
    try:
        brut = await vision.completer(messages, max_tokens=200)
    except ServiceIndisponible as erreur:
        _dire(f"ra-vision injoignable : {erreur.detail}")
        return 1

    _dire(f"\nsortie brute du modèle :\n  {brut}")
    boites = extraire_boites(
        brut,
        cible=arguments.cible,
        largeur_photo=image.width,
        hauteur_photo=image.height,
        min_pixels=MIN_PIXELS,
        max_pixels=MAX_PIXELS,
    )
    _dire(f"\n{len(boites)} boîte(s) en pixels de la photo :")
    for boite in boites:
        _dire(f"  {boite['label']:24s} {boite['bbox']}")

    if arguments.attendu:
        attendue = [int(v) for v in arguments.attendu.split(",")]
        if boites:
            derive = max(abs(a - b) for a, b in zip(boites[0]["bbox"], attendue))
            _dire(f"\nboîte de référence : {attendue}")
            _dire(f"dérive maximale : {derive} px")
            seuil = max(10, image.width // 50)
            _dire("CONFORME" if derive <= seuil else f"DÉRIVE au-delà du seuil de {seuil} px")
            return 0 if derive <= seuil else 1
        _dire("\naucune boîte produite : comparaison impossible")
        return 1

    if arguments.sortie and boites:
        from rda.ra.localisation import dessiner

        arguments.sortie.write_bytes(en_octets(dessiner(image, boites)))
        _dire(f"\nimage annotée écrite dans {arguments.sortie}")
    return 0


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--auto", action="store_true", help="vérification hors ligne")
    analyseur.add_argument("--image", type=Path, help="photo à envoyer au modèle")
    analyseur.add_argument("--cible", default="roulement")
    analyseur.add_argument("--attendu", help="boîte de référence « x1,y1,x2,y2 »")
    analyseur.add_argument("--url-vision", default=None)
    analyseur.add_argument("--sortie", type=Path, help="où écrire l'image annotée")
    arguments = analyseur.parse_args(argv)

    if arguments.image:
        return asyncio.run(calibrer_en_ligne(arguments))
    # Sans --image, la verification hors ligne est le comportement par defaut : elle ne demande
    # aucun service et repond a la question « la reconstruction de la grille tient-elle ? ».
    return calibrer_hors_ligne()


if __name__ == "__main__":
    sys.exit(main())
