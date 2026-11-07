"""Routes du module RA, montees sous /api/v1/ra.

Toutes exigent l'authentification KALATI et journalisent leur appel. Aucune n'accepte d'en-tete
d'habilitation : les groupes viennent de la session.

Specification : docs/spec-module-ra.md, section 7.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from rda.ra import journal as journal_ra
from rda.ra.agent import AgentRA as MoteurRA
from rda.ra.clients import ServiceIndisponible
from rda.ra.config import obtenir_parametres_ra
from rda.ra.etat import etat_ra
from rda.ra.images import en_octets, preparer
from rda.ra.localisation import dessiner
from rda.ra.schemas import (
    DocumentSortie,
    EquipementSortie,
    PhotoVersee,
    ReponseLocalisation,
    ReponseRA,
)
from rda.ra.securite import AgentRA, agent_courant, exiger_administrateur_ra, verifier_acces_element

routeur = APIRouter(prefix="/ra", tags=["ra"])

TYPES_IMAGE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def obtenir_moteur() -> MoteurRA:
    """Moteur du module. Remplacable en test par surcharge de dependance."""
    return MoteurRA(etat_ra)


def _exiger_artefacts() -> None:
    if not etat_ra.charge:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Les artefacts du module RA ne sont pas chargés.",
        )


def _adresse(requete: Request) -> str | None:
    return requete.client.host if requete.client else None


async def _lire_photo(photo: UploadFile | None) -> tuple[Any, bytes] | tuple[None, None]:
    """Lit, controle et redresse une photo transmise en multipart."""
    if photo is None:
        return None, None
    donnees = await photo.read()
    image, jpeg = preparer(donnees, photo.content_type)
    return image, jpeg


# --------------------------------------------------------------------------- question


@routeur.post("/question", response_model=ReponseRA)
async def poser_question(
    requete: Request,
    question: Annotated[str, Form()],
    equipement: Annotated[str | None, Form()] = None,
    date_reference: Annotated[str | None, Form()] = None,
    photo: Annotated[UploadFile | None, File()] = None,
    agent: AgentRA = Depends(agent_courant),
    moteur: MoteurRA = Depends(obtenir_moteur),
) -> ReponseRA:
    """Question sur un equipement, avec photo facultative. Reponse citee ou abstention."""
    _exiger_artefacts()
    depart = time.monotonic()
    image, jpeg = await _lire_photo(photo)

    try:
        resultat = await moteur.repondre(
            question,
            groupes=agent.groupes,
            equipement=equipement or None,
            photo_jpeg=jpeg,
            date_reference=date_reference or None,
            dimensions_photo=(image.width, image.height) if image else None,
        )
    except ServiceIndisponible as erreur:
        await journal_ra.enregistrer(
            action="QUESTION",
            agent_courriel=agent.courriel,
            groupes=agent.groupes,
            resultat="ERREUR",
            equipement_id=equipement,
            latence_ms=int((time.monotonic() - depart) * 1000),
            adresse_ip=_adresse(requete),
            detail=erreur.detail,
        )
        raise

    # Photo annotee : on ne la produit que s'il y a quelque chose a montrer.
    if resultat.get("boites") and image is not None:
        parametres = obtenir_parametres_ra()
        parametres.depot_dir.mkdir(parents=True, exist_ok=True)
        nom = f"loc_{uuid4().hex}.jpg"
        (parametres.depot_dir / nom).write_bytes(en_octets(dessiner(image, resultat["boites"])))
        resultat["image_annotee"] = f"depot/{nom}"

    await journal_ra.enregistrer(
        action="QUESTION",
        agent_courriel=agent.courriel,
        groupes=agent.groupes,
        equipement_id=resultat.get("equipement"),
        mode=resultat.get("mode"),
        confiance=resultat.get("confiance"),
        seuil=resultat.get("seuil"),
        nb_citations=len(resultat.get("citations") or []),
        latence_ms=int((time.monotonic() - depart) * 1000),
        adresse_ip=_adresse(requete),
        detail={
            "avec_photo": jpeg is not None,
            "cible": resultat.get("cible"),
            "nb_boites": len(resultat.get("boites") or []),
        },
    )
    return ReponseRA(**resultat)


# --------------------------------------------------------------------------- localisation


@routeur.post("/localiser", response_model=ReponseLocalisation)
async def localiser_composant(
    requete: Request,
    photo: Annotated[UploadFile, File()],
    cible: Annotated[str, Form()],
    agent: AgentRA = Depends(agent_courant),
    moteur: MoteurRA = Depends(obtenir_moteur),
) -> ReponseLocalisation:
    """Situe un composant sur la photo et rend les boites en pixels de la photo d'origine."""
    _exiger_artefacts()
    depart = time.monotonic()
    image, jpeg = await _lire_photo(photo)

    resultat = await moteur.localiser(jpeg, cible, image.width, image.height)

    reference = None
    if resultat["boites"]:
        parametres = obtenir_parametres_ra()
        parametres.depot_dir.mkdir(parents=True, exist_ok=True)
        nom = f"loc_{uuid4().hex}.jpg"
        (parametres.depot_dir / nom).write_bytes(en_octets(dessiner(image, resultat["boites"])))
        reference = f"depot/{nom}"

    await journal_ra.enregistrer(
        action="LOCALISER",
        agent_courriel=agent.courriel,
        groupes=agent.groupes,
        latence_ms=int((time.monotonic() - depart) * 1000),
        adresse_ip=_adresse(requete),
        detail={"cible": cible, "nb_boites": len(resultat["boites"])},
    )
    return ReponseLocalisation(
        cible=resultat["cible"],
        boites=resultat["boites"],
        largeur_photo=image.width,
        hauteur_photo=image.height,
        image_annotee=reference,
        latence_s=resultat["latence_s"],
    )


# --------------------------------------------------------------------------- referentiel


@routeur.get("/equipements", response_model=list[EquipementSortie])
async def lister_equipements(agent: AgentRA = Depends(agent_courant)) -> list[EquipementSortie]:
    """Equipements visibles par cet agent, avec leurs compteurs."""
    _exiger_artefacts()
    return [EquipementSortie(**e) for e in etat_ra.equipements_visibles(agent.groupes)]


@routeur.get("/equipements/{equipement_id}/documents", response_model=list[DocumentSortie])
async def lister_documents(
    equipement_id: str, agent: AgentRA = Depends(agent_courant)
) -> list[DocumentSortie]:
    """Documents d'un equipement, filtres par habilitation."""
    _exiger_artefacts()
    equipement = etat_ra.equipements.get(equipement_id)
    if equipement is None or equipement.get("groupe") not in set(agent.groupes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Équipement introuvable.")

    par_document: dict[str, list[dict[str, Any]]] = {}
    for element in etat_ra.elements:
        if element["equipement_id"] != equipement_id:
            continue
        if element["groupe"] not in set(agent.groupes):
            continue
        par_document.setdefault(element["cle_doc"], []).append(element)

    documents = []
    for cle, elements in sorted(par_document.items()):
        pages = [e["page_debut"] for e in elements if e["page_debut"] is not None]
        premier = elements[0]
        documents.append(
            DocumentSortie(
                cle_doc=cle,
                titre_doc=premier["titre_doc"],
                type_doc=premier["type_doc"],
                indice=premier["indice"],
                date_effet=str(premier["date_effet"]) if premier["date_effet"] else None,
                date_abrogation=(
                    str(premier["date_abrogation"]) if premier["date_abrogation"] else None
                ),
                nb_elements=len(elements),
                nb_images=sum(1 for e in elements if e["chemin_image"]),
                page_min=min(pages) if pages else None,
                page_max=max(pages) if pages else None,
            )
        )
    return documents


# --------------------------------------------------------------------------- photos et images


@routeur.post(
    "/equipements/{equipement_id}/photos",
    response_model=PhotoVersee,
    status_code=status.HTTP_201_CREATED,
)
async def verser_photo(
    requete: Request,
    equipement_id: str,
    photo: Annotated[UploadFile, File()],
    agent: AgentRA = Depends(agent_courant),
) -> PhotoVersee:
    """Depose une photo terrain rattachee a un equipement."""
    _exiger_artefacts()
    equipement = etat_ra.equipements.get(equipement_id)
    if equipement is None or equipement.get("groupe") not in set(agent.groupes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Équipement introuvable.")

    image, jpeg = await _lire_photo(photo)
    parametres = obtenir_parametres_ra()
    parametres.depot_dir.mkdir(parents=True, exist_ok=True)

    identifiant = uuid4().hex
    nom = f"photo_{equipement_id}_{identifiant}.jpg"
    (parametres.depot_dir / nom).write_bytes(jpeg)

    await journal_ra.enregistrer(
        action="PHOTO",
        agent_courriel=agent.courriel,
        groupes=agent.groupes,
        equipement_id=equipement_id,
        adresse_ip=_adresse(requete),
        detail={"taille_octets": len(jpeg), "dimensions": [image.width, image.height]},
    )
    return PhotoVersee(
        id_photo=identifiant,
        equipement_id=equipement_id,
        ref_objet=f"depot/{nom}",
        largeur=image.width,
        hauteur=image.height,
        taille_octets=len(jpeg),
    )


@routeur.get("/images/{chemin:path}")
async def lire_image(chemin: str, agent: AgentRA = Depends(agent_courant)) -> FileResponse:
    """Sert une image de source ou un depot, apres controle d'habilitation.

    Deux familles de chemins : « images/... » designe une image du corpus, dont l'habilitation
    est celle de l'element porteur ; « depot/... » designe une image produite pour cet agent.
    """
    _exiger_artefacts()
    parametres = obtenir_parametres_ra()

    if chemin.startswith("depot/"):
        racine, relatif = parametres.depot_dir, chemin.removeprefix("depot/")
    else:
        racine, relatif = etat_ra.dossier, chemin
        element = etat_ra.element_par_image(chemin)
        if element is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image introuvable.")
        verifier_acces_element(element, agent)

    # Le chemin vient du client : on verifie qu'il ne sort pas de la racine autorisee.
    fichier = (Path(racine) / relatif).resolve()
    if not fichier.is_file() or not fichier.is_relative_to(Path(racine).resolve()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image introuvable.")

    return FileResponse(
        fichier, media_type=TYPES_IMAGE.get(fichier.suffix.lower(), "application/octet-stream")
    )


# --------------------------------------------------------------------------- administration


@routeur.get("/admin/journal")
async def lire_journal(
    limite: int = 100, agent: AgentRA = Depends(exiger_administrateur_ra)
) -> dict[str, Any]:
    """Dernieres entrees du journal du module."""
    return {"items": await journal_ra.lire(limite=min(limite, 500))}


@routeur.get("/admin/politique")
async def lire_politique(_: AgentRA = Depends(exiger_administrateur_ra)) -> dict[str, Any]:
    """Politique active : seuils, poids des canaux et version."""
    _exiger_artefacts()
    politique = dict(etat_ra.politique)
    # Les deux prompts sont volumineux et ne servent pas au pilotage : on n'expose que leur taille.
    for cle in ("prompt_systeme", "prompt_description"):
        if cle in politique:
            politique[f"{cle}_longueur"] = len(politique.pop(cle))
    return politique
