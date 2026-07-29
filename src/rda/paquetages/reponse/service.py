from dataclasses import dataclass
from datetime import date
import re

from rda.commun.types import ModeReponse
from rda.infra.inference import ClientInference
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
    del seuil_generatif
    if confiance < seuil:
        return ModeReponse.ABSTENTION
    return ModeReponse.GENERATIF


SALUTATIONS = {
    "bonjour",
    "bonsoir",
    "salut",
    "hello",
    "yo",
    "merci",
    "merci beaucoup",
    "qui es-tu",
    "qui es tu",
    "que sais-tu faire",
    "que sais tu faire",
    "tu fais quoi",
}


class ServiceReponse:
    """Orchestre comprehension, recherche, reclassement, deliberation et redaction."""

    def __init__(self, politique: Politique | None = None, passages_demo: list[PassageIndexe] | None = None):
        self.politique = politique or Politique.initiale()
        self.passages_demo = passages_demo or []
        self.inference = ClientInference()
        self.derniere_trace: TraceAnalyse | None = None

    async def repondre(
        self,
        *,
        question: str,
        groupes_resolus: list[str],
        date_reference: date | None = None,
    ) -> ReponseQuestion:
        if self._est_conversationnel(question):
            return ReponseQuestion(
                mode=ModeReponse.GENERATIF.value,
                reponse=(
                    "Bonjour. Je réponds à vos questions sur les textes normatifs de CAMRAIL "
                    "en citant mes sources. Posez-moi une question documentaire précise."
                ),
                confiance=1.0,
                seuil=0.0,
                perimetre="CONVERSATION",
                citations=[],
            )

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
        if mode == ModeReponse.GENERATIF:
            texte = await self._generer_reponse(question, retenus)
        else:
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

    def _est_conversationnel(self, question: str) -> bool:
        normalisee = question.strip().lower()
        for ponctuation in ("?", "!", ".", ",", ";", ":"):
            normalisee = normalisee.replace(ponctuation, "")
        normalisee = " ".join(normalisee.split())
        return normalisee in SALUTATIONS

    async def _generer_reponse(self, question: str, retenus: list[PassageReclasse]) -> str:
        contexte = "\n\n".join(
            f"[{rang}] {retenu.candidat.passage.reference_normative}, page {retenu.candidat.passage.page}\n"
            f"{retenu.candidat.passage.texte[:1800]}"
            for rang, retenu in enumerate(retenus[:3], start=1)
        )
        systeme = (
            "Tu es l'assistant documentaire KALATI. Réponds en français avec une synthèse courte "
            "de 3 à 6 phrases maximum. Cite les sources sous la forme [1], [2] quand tu utilises "
            "un extrait. Ne recopie jamais les extraits in extenso, ne liste pas des blocs bruts, "
            "et n'invente rien hors du contexte fourni."
        )
        try:
            reponse = await self.inference.generer(
                systeme=systeme,
                contexte=contexte,
                question=question,
                max_tokens=300,
            )
        except Exception:
            return self._reponse_locale_courte(retenus)

        reponse = reponse.strip()
        if self._semble_bloc_documentaire(reponse):
            return self._reponse_locale_courte(retenus)
        if not re.search(r"\[\d+\]", reponse) and retenus:
            reponse = f"{reponse} [1]"
        return reponse

    def _semble_bloc_documentaire(self, reponse: str) -> bool:
        lignes = [ligne for ligne in reponse.splitlines() if ligne.strip()]
        marqueurs_bruts = (
            "EPSF :",
            "JOURNAL OFFICIEL",
            "INTITULE DE LA MATIERE",
            "INTITULÉ DE LA MATIÈRE",
            "Source: [",
        )
        return (
            len(reponse) > 900
            or len(lignes) > 8
            or bool(re.search(r"\b\d{3}\s*\.\d\b", reponse))
            or any(marqueur in reponse for marqueur in marqueurs_bruts)
        )

    def _reponse_locale_courte(self, retenus: list[PassageReclasse]) -> str:
        if not retenus:
            return rediger(ModeReponse.ABSTENTION, retenus)

        passage = retenus[0].candidat.passage
        texte = " ".join(passage.texte.split())
        consigne = self._extraire_consigne(texte)
        if consigne:
            return f"{consigne} [1]"

        phrases = re.split(r"(?<=[.!?])\s+", texte)
        phrases_utiles = [
            phrase
            for phrase in phrases
            if len(phrase) >= 40
            and not phrase.startswith(("EPSF", "RC ", "DC ", "FORM", "COR "))
            and "JOURNAL OFFICIEL" not in phrase
        ][:3]
        if not phrases_utiles:
            phrases_utiles = [texte[:450].strip()]

        resume = " ".join(phrases_utiles)
        if len(resume) > 700:
            resume = resume[:700].rsplit(" ", 1)[0] + "."
        return f"{resume} [{1}]"

    def _extraire_consigne(self, texte: str) -> str | None:
        obligations: list[str] = []
        for motif in (r"le conducteur doit\s+(.+?)(?=\.|;| Toutefois| Sur voie|$)", r"Le conducteur\s*:\s*(.+?)(?=Autre cas|$)"):
            correspondance = re.search(motif, texte, flags=re.IGNORECASE)
            if correspondance:
                extrait = correspondance.group(1)
                extrait = re.sub(r"\s*[-•]\s*", ", ", extrait)
                extrait = extrait.strip(" :;,.")
                if extrait:
                    obligations.append(f"Le conducteur doit {extrait}.")
                break

        exception = re.search(r"Toutefois\s+(.+?)(?=\.\s|$)", texte, flags=re.IGNORECASE)
        if exception:
            obligations.append(f"Exception ou allègement possible : {exception.group(1).strip(' :;,.')}.")

        if not obligations:
            return None
        obligations.append("La consigne exacte doit être appliquée selon le type de ligne et la situation rencontrée.")
        return " ".join(obligations[:3])

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
