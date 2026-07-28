from enum import StrEnum


class StatutAgent(StrEnum):
    ACTIF = "ACTIF"
    SUSPENDU = "SUSPENDU"


class CanalSession(StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"
    API = "API"


class OrigineGroupe(StrEnum):
    POSTE = "POSTE"
    EXCEPTION = "EXCEPTION"


class TypePassage(StrEnum):
    TEXTE = "TEXTE"
    TABLEAU = "TABLEAU"
    FIGURE = "FIGURE"


class StatutVersion(StrEnum):
    BROUILLON = "BROUILLON"
    EN_VIGUEUR = "EN_VIGUEUR"
    ABROGEE = "ABROGEE"


class ModeReponse(StrEnum):
    ABSTENTION = "ABSTENTION"
    EXTRACTIF = "EXTRACTIF"
    GENERATIF = "GENERATIF"


class ResultatAudit(StrEnum):
    SUCCES = "SUCCES"
    REFUS = "REFUS"
    ERREUR = "ERREUR"

