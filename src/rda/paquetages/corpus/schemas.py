from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentEntree(BaseModel):
    reference_kalati: str
    titre: str
    type_document: str
    perimetre_metier: str
    ref_structure: UUID | None = None


class TacheIngestionSortie(BaseModel):
    id_tache: UUID | None = None
    statut: str
    date_creation: datetime | None = None


class AbrogationEntree(BaseModel):
    date_abrogation: date


class SeuilEntree(BaseModel):
    perimetre_metier: str
    seuil_abstention: float
    k_recuperation: int = 60
    poids_dense: float = 0.5
    poids_lexical: float = 0.5
    nb_citations_min: int = 1

