"""Routes FastAPI exposees par ce paquetage fonctionnel."""

from uuid import UUID

from fastapi import APIRouter, File, UploadFile, status

from rda.paquetages.corpus.schemas import AbrogationEntree, DocumentEntree, SeuilEntree, TacheIngestionSortie
from rda.paquetages.corpus.service import ServiceCorpus

routeur = APIRouter(tags=["administration-corpus"])


@routeur.post("/admin/documents", response_model=TacheIngestionSortie, status_code=status.HTTP_201_CREATED)
async def verser_document(metadonnees: DocumentEntree, fichier: UploadFile = File(...)) -> TacheIngestionSortie:
    del fichier
    return await ServiceCorpus().creer_tache_ingestion(metadonnees)


@routeur.post("/admin/documents/{id_document}/versions", status_code=status.HTTP_201_CREATED)
async def creer_version(id_document: UUID, fichier: UploadFile = File(...)) -> dict:
    del fichier
    return {"id_document": id_document, "statut": "EN_ATTENTE"}


@routeur.post("/admin/versions/{id_version}/abrogation")
async def abroger_version(id_version: UUID, entree: AbrogationEntree) -> dict:
    return {"id_version": id_version, "date_abrogation": entree.date_abrogation}


@routeur.delete("/admin/documents/{id_document}")
async def supprimer_document(id_document: UUID) -> dict:
    return await ServiceCorpus().supprimer_logiquement(id_document)


@routeur.get("/admin/taches")
async def lister_taches() -> dict:
    return {"items": []}


@routeur.post("/admin/taches/{id_tache}/reprise")
async def reprendre_tache(id_tache: UUID) -> dict:
    return {"id_tache": id_tache, "statut": "EN_ATTENTE"}


@routeur.put("/admin/seuils")
async def modifier_seuils(entree: SeuilEntree) -> dict:
    return entree.model_dump()


@routeur.get("/admin/glossaire")
async def lire_glossaire() -> dict:
    return {"items": []}


@routeur.post("/admin/glossaire", status_code=status.HTTP_201_CREATED)
async def creer_terme(entree: dict) -> dict:
    return entree

