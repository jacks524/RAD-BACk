"""Construction du message transmis au modele de vision-langage.

Portage fidele de la cellule 31. L'ordre des elements du message n'est pas indifferent : les
images des sources viennent d'abord, chacune annoncee par son numero, puis la photo du technicien,
puis le texte des sources, puis la question. Le modele lit dans cet ordre.

La photo du technicien est explicitement declaree non citable. C'est ce qui empeche le modele de
presenter comme une source ce que le technicien lui a montre : une photo de terrain documente la
situation, elle ne fait pas autorite sur la procedure.
"""

from __future__ import annotations

from typing import Any

from rda.ra.clients import ClientVision
from rda.ra.lisibilite import extraire_pertinent, nettoyer
from rda.ra.recherche import Candidat

# Longueurs de troncature du notebook : 1200 caracteres par source dans le contexte.
MAX_CARACTERES_SOURCE = 1200
# Mode extractif : on restitue le debut de la meilleure source, suivi de sa citation.
MAX_CARACTERES_EXTRAIT = 900

MENTION_PHOTO_TECHNICIEN = (
    "↑ Photo prise sur le terrain par le technicien (contexte, non citable)."
)


def construire_messages(
    question: str,
    retenus: list[Candidat],
    elements: list[dict[str, Any]],
    *,
    prompt_systeme: str,
    max_images: int,
    dossier_artefacts,
    photo_jpeg: bytes | None = None,
) -> list[dict[str, Any]]:
    """Assemble le dialogue systeme + utilisateur au format multimodal.

    Les images des sources sont lues depuis le dossier d'artefacts et transmises en base64 : le
    service de vision ne recoit jamais de chemin, donc ne peut pas lire autre chose que ce qu'on
    lui remet.
    """
    contenu: list[dict[str, Any]] = []
    blocs: list[str] = []
    images_jointes = 0

    for numero, candidat in enumerate(retenus, start=1):
        element = elements[candidat.position]
        chemin_image = element.get("chemin_image")
        if chemin_image and images_jointes < max_images:
            fichier = dossier_artefacts / chemin_image
            if fichier.is_file():
                contenu.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": ClientVision.image_en_url(fichier.read_bytes())},
                    }
                )
                contenu.append({"type": "text", "text": f"↑ Image de la source [{numero}]."})
                images_jointes += 1
        blocs.append(
            f"[{numero}] {element['reference']}\n"
            + extraire_pertinent(element["texte"], question, max_caracteres=MAX_CARACTERES_SOURCE)
        )

    if photo_jpeg is not None:
        contenu.append(
            {"type": "image_url", "image_url": {"url": ClientVision.image_en_url(photo_jpeg)}}
        )
        contenu.append({"type": "text", "text": MENTION_PHOTO_TECHNICIEN})

    contenu.append(
        {
            "type": "text",
            "text": "Sources :\n\n" + "\n\n".join(blocs) + f"\n\nQuestion : {question}",
        }
    )

    return [
        {"role": "system", "content": prompt_systeme},
        {"role": "user", "content": contenu},
    ]


def reponse_extractive(
    retenus: list[Candidat], elements: list[dict[str, Any]], question: str = ""
) -> str:
    """Restitution de la meilleure source, nettoyee, recentree sur la question, citee.

    Aucun modele n'intervient : le texte reste celui du document. Deux traitements s'ajoutent
    pourtant a la troncature du notebook, parce que sans eux la reponse est inutilisable sur le
    terrain — l'habillage de page en tete (adresse du site, titre courant, bandeau vertical capte
    a l'envers par l'OCR) et un debut de section qui ne repond pas a la question posee.

    Le texte n'est ni reformule ni resume : ce qui est affiche se retrouve mot pour mot dans le
    manuel, a la page citee.
    """
    if not retenus:
        return ""
    texte = elements[retenus[0].position]["texte"]
    extrait = (
        extraire_pertinent(texte, question, max_caracteres=MAX_CARACTERES_EXTRAIT)
        if question
        else nettoyer(texte)[:MAX_CARACTERES_EXTRAIT]
    )
    return f"{extrait} [1]"
