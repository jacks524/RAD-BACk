"""Module backend RDA consacre a reclassement."""

from dataclasses import dataclass
from math import exp

from rda.paquetages.reponse.recherche import CandidatRecherche


@dataclass(frozen=True)
class PassageReclasse:
    candidat: CandidatRecherche
    score_reclassement: float


def sigmoide(valeur: float) -> float:
    return 1 / (1 + exp(-valeur))


def reclasser(candidats: list[CandidatRecherche], limite: int = 30) -> tuple[list[PassageReclasse], float]:
    retenus = candidats[:limite]
    reclasses = [
        PassageReclasse(c, 4 * c.score_lexical + 2 * c.score_dense + 80 * c.score_fusion)
        for c in retenus
    ]
    reclasses.sort(key=lambda r: r.score_reclassement, reverse=True)
    if not reclasses:
        return [], 0.0
    probabilites = [sigmoide(r.score_reclassement - 3.0) for r in reclasses[:3]]
    confiance = 0.7 * probabilites[0] + 0.3 * (sum(probabilites) / len(probabilites))
    return reclasses, confiance

