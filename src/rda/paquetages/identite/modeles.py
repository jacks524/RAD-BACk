"""Modeles SQLAlchemy representant les tables de ce paquetage fonctionnel."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rda.infra.bases import BaseIdentite


class Structure(BaseIdentite):
    __tablename__ = "structures"

    id_structure: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    libelle: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50))
    id_parent: Mapped[UUID | None] = mapped_column(ForeignKey("structures.id_structure"))


class Poste(BaseIdentite):
    __tablename__ = "postes"

    id_poste: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    libelle: Mapped[str] = mapped_column(String(255))
    famille_metier: Mapped[str] = mapped_column(String(100))
    niveau_hierarchique: Mapped[int] = mapped_column(Integer)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentCamrail(BaseIdentite):
    __tablename__ = "agents"

    id_agent: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    matricule: Mapped[str] = mapped_column(String(50), unique=True)
    nom: Mapped[str] = mapped_column(String(120))
    prenom: Mapped[str] = mapped_column(String(120))
    courriel: Mapped[str] = mapped_column(String(255), unique=True)
    empreinte_mdp: Mapped[str] = mapped_column(String(255))
    id_poste: Mapped[UUID] = mapped_column(ForeignKey("postes.id_poste"))
    id_structure: Mapped[UUID] = mapped_column(ForeignKey("structures.id_structure"))
    statut: Mapped[str] = mapped_column(String(30), default="ACTIF")
    reference_annuaire: Mapped[str | None] = mapped_column(String(255))


class Role(BaseIdentite):
    __tablename__ = "roles"

    id_role: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    libelle: Mapped[str] = mapped_column(String(255))


class GroupeSecurite(BaseIdentite):
    __tablename__ = "groupes_securite"

    id_groupe: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    libelle: Mapped[str] = mapped_column(String(255))
    niveau_confidentialite: Mapped[int] = mapped_column(Integer)
    perimetre_metier: Mapped[str] = mapped_column(String(80))


class PosteGroupe(BaseIdentite):
    __tablename__ = "postes_groupes"

    id_poste: Mapped[UUID] = mapped_column(ForeignKey("postes.id_poste"), primary_key=True)
    id_groupe: Mapped[UUID] = mapped_column(
        ForeignKey("groupes_securite.id_groupe"), primary_key=True
    )
    date_activation: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentRole(BaseIdentite):
    __tablename__ = "agents_roles"

    id_agent: Mapped[UUID] = mapped_column(ForeignKey("agents.id_agent"), primary_key=True)
    id_role: Mapped[int] = mapped_column(ForeignKey("roles.id_role"), primary_key=True)
    date_attribution: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentGroupe(BaseIdentite):
    __tablename__ = "agents_groupes"

    id_agent: Mapped[UUID] = mapped_column(ForeignKey("agents.id_agent"), primary_key=True)
    id_groupe: Mapped[UUID] = mapped_column(
        ForeignKey("groupes_securite.id_groupe"), primary_key=True
    )
    origine: Mapped[str] = mapped_column(String(20), primary_key=True)
    date_attribution: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(BaseIdentite):
    __tablename__ = "sessions"

    id_session: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_agent: Mapped[UUID] = mapped_column(ForeignKey("agents.id_agent"))
    empreinte_jeton: Mapped[str] = mapped_column(String(255), unique=True)
    canal: Mapped[str] = mapped_column(String(30))
    groupes_resolus: Mapped[dict] = mapped_column(JSONB)
    adresse_ip: Mapped[str | None] = mapped_column(String(80))
    date_ouverture: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_expiration: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_revocation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntreeJournal(BaseIdentite):
    __tablename__ = "journal_audit"

    id_entree: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ref_agent: Mapped[UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(100))
    entite_cible: Mapped[str | None] = mapped_column(String(255))
    adresse_ip: Mapped[str | None] = mapped_column(String(80))
    resultat: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class JournalAccesDocument(BaseIdentite):
    __tablename__ = "journal_acces_document"

    id_acces: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id_agent: Mapped[UUID] = mapped_column()
    ref_version: Mapped[UUID] = mapped_column()
    ref_message: Mapped[UUID] = mapped_column()
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True))

