"""Schemas Pydantic definissant les contrats d entree et de sortie de ce paquetage."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class CitationSortie(BaseModel):
    rang: int
    reference_normative: str
    extrait_affiche: str
    id_passage: UUID
    id_version: UUID
    page: int


class QuestionEntree(BaseModel):
    question: str = Field(min_length=1)
    id_conversation: UUID | None = None
    date_reference: date | None = None
    canal: str = "WEB"


class ReponseQuestion(BaseModel):
    mode: str
    reponse: str
    confiance: float
    seuil: float
    perimetre: str
    citations: list[CitationSortie]


class SignalementEntree(BaseModel):
    type_probleme: str
    commentaire: str | None = None


class SyntheseVocaleEntree(BaseModel):
    texte: str = Field(min_length=1, max_length=1200)


class SourceSortie(BaseModel):
    id_passage: UUID
    id_version: UUID
    reference_normative: str
    page: int
    url: str
