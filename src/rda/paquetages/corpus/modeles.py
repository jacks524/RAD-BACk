from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rda.infra.bases import BaseCorpus, VecteurPg


class Document(BaseCorpus):
    __tablename__ = "documents"

    id_document: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reference_kalati: Mapped[str] = mapped_column(String(120), unique=True)
    titre: Mapped[str] = mapped_column(String(500))
    type_document: Mapped[str] = mapped_column(String(80))
    perimetre_metier: Mapped[str] = mapped_column(String(80))
    ref_structure: Mapped[UUID | None] = mapped_column()
    supprime: Mapped[bool] = mapped_column(Boolean, default=False)

    versions: Mapped[list["VersionDocument"]] = relationship(back_populates="document")


class VersionDocument(BaseCorpus):
    __tablename__ = "versions_document"
    __table_args__ = (
        UniqueConstraint("id_document", "indice"),
        Index("ix_versions_document_dates", "date_effet", "date_abrogation"),
    )

    id_version: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_document: Mapped[UUID] = mapped_column(ForeignKey("documents.id_document"))
    indice: Mapped[str] = mapped_column(String(40))
    date_effet: Mapped[date] = mapped_column(Date)
    date_abrogation: Mapped[date | None] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(40))
    empreinte_fichier: Mapped[str] = mapped_column(String(64))
    reference_stockage: Mapped[str] = mapped_column(String(500))
    nb_pages: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="versions")


class HabilitationDocument(BaseCorpus):
    __tablename__ = "habilitations_document"

    id_document: Mapped[UUID] = mapped_column(ForeignKey("documents.id_document"), primary_key=True)
    ref_groupe: Mapped[UUID] = mapped_column(primary_key=True)
    niveau_minimum: Mapped[int] = mapped_column(Integer)
    cache_terminal: Mapped[bool] = mapped_column(Boolean, default=False)


class Page(BaseCorpus):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("id_version", "numero"),)

    id_page: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_version: Mapped[UUID] = mapped_column(ForeignKey("versions_document.id_version"))
    numero: Mapped[int] = mapped_column(Integer)
    texte_brut: Mapped[str] = mapped_column(Text)
    reference_image: Mapped[str | None] = mapped_column(String(500))


class Passage(BaseCorpus):
    __tablename__ = "passages"
    __table_args__ = (
        Index("ix_passages_vecteur_hnsw", "vecteur", postgresql_using="hnsw", postgresql_ops={"vecteur": "vector_cosine_ops"}),
        Index("ix_passages_index_lexical", "index_lexical", postgresql_using="gin"),
    )

    id_passage: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_version: Mapped[UUID] = mapped_column(ForeignKey("versions_document.id_version"))
    ordre: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    chemin_hierarchique: Mapped[str] = mapped_column(String(500))
    page_debut: Mapped[int] = mapped_column(Integer)
    page_fin: Mapped[int] = mapped_column(Integer)
    texte: Mapped[str] = mapped_column(Text)
    vecteur: Mapped[list[float] | None] = mapped_column(VecteurPg(768))
    index_lexical: Mapped[str | None] = mapped_column(TSVECTOR)
    nb_jetons: Mapped[int] = mapped_column(Integer)


class Tableau(BaseCorpus):
    __tablename__ = "tableaux"

    id_tableau: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_passage: Mapped[UUID] = mapped_column(ForeignKey("passages.id_passage"), unique=True)
    contenu_markdown: Mapped[str] = mapped_column(Text)
    structure_json: Mapped[dict] = mapped_column(JSONB)
    nb_lignes: Mapped[int] = mapped_column(Integer)
    nb_colonnes: Mapped[int] = mapped_column(Integer)


class Figure(BaseCorpus):
    __tablename__ = "figures"

    id_figure: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_passage: Mapped[UUID] = mapped_column(ForeignKey("passages.id_passage"), unique=True)
    reference_image: Mapped[str] = mapped_column(String(500))
    legende_generee: Mapped[str | None] = mapped_column(Text)
    texte_ocr: Mapped[str | None] = mapped_column(Text)
    fiabilite_extraction: Mapped[float | None] = mapped_column()


class TermeMetier(BaseCorpus):
    __tablename__ = "termes_metier"

    id_terme: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    terme: Mapped[str] = mapped_column(String(120), unique=True)
    definition: Mapped[str] = mapped_column(Text)
    synonymes: Mapped[dict] = mapped_column(JSONB, default=dict)
    ref_version_source: Mapped[UUID | None] = mapped_column()
    perimetre_metier: Mapped[str] = mapped_column(String(80))
    prononciations: Mapped[dict] = mapped_column(JSONB, default=dict)


class TacheIngestion(BaseCorpus):
    __tablename__ = "taches_ingestion"

    id_tache: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    statut: Mapped[str] = mapped_column(String(40))
    reference_stockage: Mapped[str] = mapped_column(String(500))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

