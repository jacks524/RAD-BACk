from dataclasses import dataclass
from datetime import date

from rda.commun.types import ModeReponse
from rda.noyau.politique import Politique
from rda.paquetages.reponse.comprehension import RequeteComprise, comprendre_question
from rda.paquetages.reponse.recherche import PassageIndexe, rechercher_hybride_en_memoire
from rda.paquetages.reponse.reclassement import PassageReclasse, reclasser
from rda.paquetages.reponse.redaction import rediger
from rda.paquetages.reponse.schemas import CitationSortie, ReponseQuestion
from rda.paquetages.reponse.verification import verifier_ancrage


@dataclass(frozen=True)
class TraceAnalyse:
    requete: RequeteComprise
    candidats: list
    retenus: list[PassageReclasse]
    confiance: float
    mode: ModeReponse
    injection_journalisee: bool


def deliberer(confiance: float, seuil: float, seuil_generatif: float) -> ModeReponse:
    if confiance < seuil:
        return ModeReponse.ABSTENTION
    if confiance < seuil_generatif:
        return ModeReponse.EXTRACTIF
    return ModeReponse.GENERATIF


class ServiceReponse:
    """Orchestre comprehension, recherche, reclassement, deliberation et redaction."""

    def __init__(self, politique: Politique | None = None, passages_demo: list[PassageIndexe] | None = None):
        self.politique = politique or Politique.initiale()
        self.passages_demo = passages_demo or []
        self.derniere_trace: TraceAnalyse | None = None

    async def repondre(
        self,
        *,
        question: str,
        groupes_resolus: list[str],
        date_reference: date | None = None,
    ) -> ReponseQuestion:
        requete = comprendre_question(question, date_reference)
        seuil = self.politique.seuil_abstention(requete.perimetre)
        candidats = rechercher_hybride_en_memoire(
            question=requete.requete_etendue,
            passages=self.passages_demo,
            groupes_resolus=groupes_resolus,
            date_reference=requete.date_reference,
        )
        retenus, confiance = reclasser(candidats)
        mode = deliberer(confiance, seuil, self.politique.seuil_generatif)
        texte = rediger(mode, retenus)

        if not verifier_ancrage(mode, texte, retenus):
            mode = ModeReponse.ABSTENTION
            texte = rediger(mode, retenus)
            citations: list[CitationSortie] = []
        else:
            citations = [] if mode == ModeReponse.ABSTENTION else self._citations(retenus)

        self.derniere_trace = TraceAnalyse(
            requete=requete,
            candidats=candidats,
            retenus=retenus,
            confiance=confiance,
            mode=mode,
            injection_journalisee=requete.injection_detectee,
        )
        return ReponseQuestion(
            mode=mode.value,
            reponse=texte,
            confiance=round(confiance, 4),
            seuil=seuil,
            perimetre=requete.perimetre,
            citations=citations,
        )

    def _citations(self, retenus: list[PassageReclasse]) -> list[CitationSortie]:
        sorties = []
        for rang, retenu in enumerate(retenus[:3], start=1):
            p = retenu.candidat.passage
            sorties.append(
                CitationSortie(
                    rang=rang,
                    reference_normative=p.reference_normative,
                    extrait_affiche=p.texte[:500],
                    id_passage=p.id_passage,
                    id_version=p.id_version,
                    page=p.page,
                )
            )
        return sorties

