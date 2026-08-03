"""Modeles SQLAlchemy representant les tables de ce paquetage fonctionnel."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rda.infra.bases import BaseIntelligence


class Conversation(BaseIntelligence):
    __tablename__ = "conversations"

    id_conversation: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ref_agent: Mapped[UUID] = mapped_column()
    titre: Mapped[str | None] = mapped_column(String(255))
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Message(BaseIntelligence):
    __tablename__ = "messages"

    id_message: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_conversation: Mapped[UUID] = mapped_column(ForeignKey("conversations.id_conversation"))
    role: Mapped[str] = mapped_column(String(30))
    question: Mapped[str | None] = mapped_column(Text)
    contenu: Mapped[str] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(30))
    confiance: Mapped[float | None] = mapped_column()
    seuil: Mapped[float | None] = mapped_column()
    perimetre: Mapped[str | None] = mapped_column(String(80))
    date_reference: Mapped[date | None] = mapped_column(Date)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    citations: Mapped[list["Citation"]] = relationship(back_populates="message")


class Citation(BaseIntelligence):
    __tablename__ = "citations"
    __table_args__ = (UniqueConstraint("id_message", "rang"),)

    id_citation: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_message: Mapped[UUID] = mapped_column(ForeignKey("messages.id_message"))
    rang: Mapped[int] = mapped_column(Integer)
    reference_normative: Mapped[str] = mapped_column(String(500))
    extrait_affiche: Mapped[str] = mapped_column(Text)
    id_passage: Mapped[UUID] = mapped_column()
    id_version: Mapped[UUID] = mapped_column()
    page: Mapped[int] = mapped_column(Integer)

    message: Mapped[Message] = relationship(back_populates="citations")


class AnalyseRequete(BaseIntelligence):
    __tablename__ = "analyses_requete"

    id_analyse: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ref_message: Mapped[UUID] = mapped_column()
    requete_normalisee: Mapped[str] = mapped_column(Text)
    requete_etendue: Mapped[str] = mapped_column(Text)
    perimetre_detecte: Mapped[str] = mapped_column(String(80))
    mode_propose: Mapped[str] = mapped_column(String(30))
    score_confiance: Mapped[float] = mapped_column()
    ref_version_seuils: Mapped[UUID | None] = mapped_column()
    nb_candidats: Mapped[int] = mapped_column(Integer)
    latence_ms: Mapped[int] = mapped_column(Integer)
    date_analyse: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysePassage(BaseIntelligence):
    __tablename__ = "analyses_passage"

    id_analyse_passage: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_analyse: Mapped[UUID] = mapped_column(ForeignKey("analyses_requete.id_analyse"))
    ref_passage: Mapped[UUID] = mapped_column()
    score_dense: Mapped[float] = mapped_column()
    score_lexical: Mapped[float] = mapped_column()
    score_fusion: Mapped[float] = mapped_column()
    rang: Mapped[int] = mapped_column(Integer)
    retenu: Mapped[bool] = mapped_column(Boolean)


class Signalement(BaseIntelligence):
    __tablename__ = "signalements"

    id_signalement: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ref_message: Mapped[UUID] = mapped_column()
    type_probleme: Mapped[str] = mapped_column(String(80))
    commentaire: Mapped[str | None] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(40), default="OUVERT")
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModeleIA(BaseIntelligence):
    __tablename__ = "modeles_ia"

    id_modele: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nom: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(80))
    quantisation: Mapped[str | None] = mapped_column(String(80))
    empreinte: Mapped[str] = mapped_column(String(128))
    consommation_w: Mapped[float | None] = mapped_column()
    date_activation: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_retrait: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VersionSeuils(BaseIntelligence):
    __tablename__ = "versions_seuils"
    __table_args__ = (UniqueConstraint("numero_version", "perimetre_metier"),)

    id_version: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    numero_version: Mapped[str] = mapped_column(String(40))
    perimetre_metier: Mapped[str] = mapped_column(String(80))
    seuil_abstention: Mapped[float] = mapped_column()
    k_recuperation: Mapped[int] = mapped_column(Integer)
    poids_dense: Mapped[float] = mapped_column()
    poids_lexical: Mapped[float] = mapped_column()
    nb_citations_min: Mapped[int] = mapped_column(Integer)
    date_activation: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JeuEvaluation(BaseIntelligence):
    __tablename__ = "jeux_evaluation"

    id_jeu: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nom: Mapped[str] = mapped_column(String(255))
    donnees: Mapped[dict] = mapped_column(JSONB, default=dict)


class ResultatEvaluation(BaseIntelligence):
    __tablename__ = "resultats_evaluation"

    id_resultat: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_jeu: Mapped[UUID] = mapped_column(ForeignKey("jeux_evaluation.id_jeu"))
    metriques: Mapped[dict] = mapped_column(JSONB, default=dict)
    date_execution: Mapped[datetime] = mapped_column(DateTime(timezone=True))

