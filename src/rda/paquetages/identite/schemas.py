from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConnexionEntree(BaseModel):
    courriel: str
    mot_de_passe: str


class AgentSortie(BaseModel):
    id_agent: UUID | None = None
    courriel: str
    nom: str = ""
    prenom: str = ""
    matricule: str = ""
    poste: str = ""
    structure: str = ""
    statut: str = "ACTIF"
    groupes_resolus: list[str] = []
    roles: list[str] = []
    droits: list[dict] = []


class AgentCreationEntree(BaseModel):
    matricule: str
    courriel: str
    nom: str
    prenom: str
    mot_de_passe: str
    poste: str = ""
    structure: str = ""
    statut: str = "ACTIF"
    groupes_poste: list[str] = ["DEMO_SECURITE"]
    habilitations_exception: list[dict] = []
    roles: list[str] = ["AGENT"]


class ConnexionSortie(BaseModel):
    jeton: str
    expiration: datetime
    agent: AgentSortie


class ProfilSortie(AgentSortie):
    pass


class GroupeEntree(BaseModel):
    code: str
    libelle: str
    niveau_confidentialite: int
    perimetre_metier: str


class PosteEntree(BaseModel):
    code: str
    libelle: str
    famille_metier: str
    niveau_hierarchique: int
    actif: bool = True
