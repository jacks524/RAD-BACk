"""Module backend RDA consacre a comprehension."""

import re
from dataclasses import dataclass
from datetime import date


MOTIFS_INJECTION = [
    re.compile(r"ignore\s+(les|toutes|vos)?\s*instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"reponds?\s+sans\s+citation", re.IGNORECASE),
    re.compile(r"oublie\s+les\s+regles", re.IGNORECASE),
]


@dataclass(frozen=True)
class RequeteComprise:
    question_originale: str
    question_normalisee: str
    requete_etendue: str
    date_reference: date
    perimetre: str
    injection_detectee: bool


def normaliser_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def detecter_injection(question: str) -> bool:
    return any(motif.search(question) for motif in MOTIFS_INJECTION)


def neutraliser_question(question: str) -> str:
    texte = question
    for motif in MOTIFS_INJECTION:
        texte = motif.sub("[instruction neutralisee]", texte)
    return texte


def detecter_perimetre(question: str) -> str:
    q = question.lower()
    if any(mot in q for mot in ("securite", "circulation", "frein", "signal")):
        return "SECURITE"
    if any(mot in q for mot in ("transport", "gare", "train")):
        return "TRANSPORT"
    if any(mot in q for mot in ("conge", "salaire", "agent", "poste")):
        return "RH"
    if any(mot in q for mot in ("contrat", "loi", "decret", "juridique")):
        return "JURIDIQUE"
    return "DEFAUT"


def comprendre_question(question: str, date_reference: date | None = None) -> RequeteComprise:
    injection = detecter_injection(question)
    question_saine = neutraliser_question(question) if injection else question
    normalisee = normaliser_question(question_saine)
    return RequeteComprise(
        question_originale=question,
        question_normalisee=normalisee,
        requete_etendue=normalisee,
        date_reference=date_reference or date.today(),
        perimetre=detecter_perimetre(normalisee),
        injection_detectee=injection,
    )

