"""Recherche hybride en memoire combinant score lexical et vecteur simplifie pour la demo."""

from dataclasses import dataclass
from datetime import date
from math import sqrt
from uuid import UUID


@dataclass(frozen=True)
class PassageIndexe:
    id_passage: UUID
    id_version: UUID
    id_document: UUID
    titre: str
    reference_normative: str
    texte: str
    page: int
    groupes_autorises: list[str]
    date_effet: date
    date_abrogation: date | None
    vecteur: list[float]


@dataclass(frozen=True)
class CandidatRecherche:
    passage: PassageIndexe
    score_dense: float
    score_lexical: float
    score_fusion: float
    rang: int


def _jetons(texte: str) -> set[str]:
    return {mot for mot in texte.lower().replace("'", " ").split() if len(mot) > 2}


def _cosinus(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    produit = sum(a[i] * b[i] for i in range(n))
    norme_a = sqrt(sum(a[i] * a[i] for i in range(n)))
    norme_b = sqrt(sum(b[i] * b[i] for i in range(n)))
    return produit / (norme_a * norme_b) if norme_a and norme_b else 0.0


def vecteur_question(question: str, dimensions: int = 8) -> list[float]:
    jetons = _jetons(question)
    return [float(sum(hash(mot + str(i)) % 17 for mot in jetons) % 101) / 100 for i in range(dimensions)]


def rechercher_hybride_en_memoire(
    *,
    question: str,
    passages: list[PassageIndexe],
    groupes_resolus: list[str],
    date_reference: date,
    k: int = 60,
    poids_dense: float = 0.5,
    poids_lexical: float = 0.5,
) -> list[CandidatRecherche]:
    """Recherche hybride equivalent testable de la requete SQL RLS + date."""

    groupes = set(groupes_resolus)
    if not groupes:
        return []

    q_jetons = _jetons(question)
    q_vecteur = vecteur_question(question, len(passages[0].vecteur) if passages else 8)
    bruts: list[tuple[PassageIndexe, float, float]] = []
    for passage in passages:
        autorise = groupes.intersection({str(g) for g in passage.groupes_autorises})
        en_vigueur = passage.date_effet <= date_reference and (
            passage.date_abrogation is None or passage.date_abrogation > date_reference
        )
        if not autorise or not en_vigueur:
            continue
        p_jetons = _jetons(passage.texte + " " + passage.titre)
        lexical = len(q_jetons.intersection(p_jetons)) / max(len(q_jetons), 1)
        dense = max(_cosinus(q_vecteur, passage.vecteur), 0.0)
        bruts.append((passage, dense, lexical))

    rang_dense = {
        p.id_passage: rang
        for rang, (p, _, _) in enumerate(sorted(bruts, key=lambda x: x[1], reverse=True), start=1)
    }
    rang_lexical = {
        p.id_passage: rang
        for rang, (p, _, _) in enumerate(sorted(bruts, key=lambda x: x[2], reverse=True), start=1)
    }

    candidats = []
    for passage, dense, lexical in bruts:
        rrf = poids_dense / (60 + rang_dense[passage.id_passage]) + poids_lexical / (
            60 + rang_lexical[passage.id_passage]
        )
        candidats.append(CandidatRecherche(passage, dense, lexical, rrf, 0))

    tries = sorted(candidats, key=lambda c: c.score_fusion, reverse=True)[:k]
    return [
        CandidatRecherche(c.passage, c.score_dense, c.score_lexical, c.score_fusion, rang)
        for rang, c in enumerate(tries, start=1)
    ]

