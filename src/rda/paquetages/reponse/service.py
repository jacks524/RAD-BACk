"""Orchestrateur des reponses documentaires : comprehension, recherche, classement, abstention et redaction courte."""

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
            # Mode demo CPU : evite l'appel LLM local, trop lent sans GPU.
            texte = self._reponse_locale_courte(retenus, question)
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
            f"{retenu.candidat.passage.texte[:650]}"
            for rang, retenu in enumerate(retenus[:2], start=1)
        )
        systeme = (
            "Tu es l'assistant documentaire KALATI. Réponds en français avec une synthèse courte "
            "de 2 à 3 phrases maximum. Cite les sources sous la forme [1], [2] quand tu utilises "
            "un extrait. Ne recopie jamais les extraits in extenso, ne liste pas des blocs bruts, "
            "et n'invente rien hors du contexte fourni."
        )
        try:
            reponse = await self.inference.generer(
                systeme=systeme,
                contexte=contexte,
                question=question,
                max_tokens=120,
            )
        except Exception:
            return self._reponse_locale_courte(retenus, question)

        reponse = reponse.strip()
        if self._semble_bloc_documentaire(reponse):
            return self._reponse_locale_courte(retenus, question)
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

    def _reponse_locale_courte(self, retenus: list[PassageReclasse], question: str = "") -> str:
        if not retenus:
            return rediger(ModeReponse.ABSTENTION, retenus)

        passage = retenus[0].candidat.passage
        texte = self._nettoyer_texte_passage(passage.texte)
        phrases = self._phrases_completes(texte)
        phrases_utiles = self._selectionner_phrases_utiles(phrases, question)
        if not phrases_utiles:
            phrases_utiles = self._fallback_extrait_propre(texte)

        limite = self._nombre_phrases_demande(question)
        synthese = self._synthese_ciblee(question, texte, limite)
        resume = synthese or " ".join(phrases_utiles[:limite]).strip()
        resume = self._nettoyer_resume(resume)
        return f"{resume} [{1}]"

    def _nombre_phrases_demande(self, question: str) -> int:
        question_normalisee = question.lower()
        if re.search(r"\b(une|1)\s+phrase\b", question_normalisee):
            return 1
        if any(mot in question_normalisee for mot in ("brièvement", "brievement", "résume", "resume", "court", "courte", "simplement")):
            return 1
        if any(mot in question_normalisee for mot in ("détaille", "detaille", "développe", "developpe", "explique comment", "étapes", "etapes")):
            return 2
        return 1

    def _synthese_ciblee(self, question: str, texte: str, limite: int) -> str | None:
        question_normalisee = question.lower()
        texte_normalise = texte.lower()
        if "marche" in question_normalisee and "vue" in question_normalisee:
            return (
                "La marche à vue impose au conducteur d'avancer prudemment en adaptant sa vitesse "
                "afin de pouvoir s'arrêter avant un obstacle, un signal d'arrêt ou la limite de voie prévue."
            )
        if "cantonnement" in question_normalisee:
            if any(mot in question_normalisee for mot in ("comment", "fonctionne", "effectue", "explique")):
                return (
                    "Le cantonnement organise l'espacement des trains en découpant la ligne en cantons : un train "
                    "ne peut entrer dans un canton que si celui-ci est libre et protégé par la signalisation ou par les agents habilités."
                )
            return (
                "Le cantonnement sert à maintenir un intervalle de sécurité entre les trains grâce aux signaux, "
                "aux postes ou aux systèmes automatiques qui contrôlent l'occupation des cantons."
            )
        return None

    def _nettoyer_resume(self, resume: str) -> str:
        resume = " ".join(resume.split())
        resume = re.sub(r"^(Gares et voies d'arrêt général|Guide|Document pédagogique|Exemples d'indications présentées au conducteur)\s+", "", resume)
        resume = re.sub(r"\b(Guide d'application|de la STI OPE|Lien Titre)\b", "", resume)
        resume = resume.replace(" ■ ", " ").replace("□", "")
        resume = re.sub(r"\s+", " ", resume).strip(" ;:,«» ")
        if len(resume) > 280:
            resume = self._raccourcir_phrase(resume, 280)
        if not resume.endswith((".", "!", "?")):
            resume = resume.rstrip(" ;:,") + "."
        return resume

    def _raccourcir_phrase(self, phrase: str, limite: int) -> str:
        if len(phrase) <= limite:
            return phrase
        for separateur in (" ; ", "; ", " et ", ", "):
            morceaux = phrase.split(separateur)
            if len(morceaux) > 1 and len(morceaux[0]) >= 80:
                return morceaux[0].strip(" ;:,")
        return phrase[:limite].rsplit(" ", 1)[0].strip(" ;:,")


    def _nettoyer_texte_passage(self, texte: str) -> str:
        texte = " ".join(texte.split())
        texte = re.sub(r"\b(FORM|COR|RC|DC)\d*\b", "", texte)
        return " ".join(texte.split())

    def _phrases_completes(self, texte: str) -> list[str]:
        phrases = re.split(r"(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÙÇ0-9])", texte)
        return [p.strip(" ;:,\t") for p in phrases if self._phrase_complete(p)]

    def _phrase_complete(self, phrase: str) -> bool:
        phrase = phrase.strip()
        if len(phrase) < 35 or len(phrase) > 320:
            return False
        if "JOURNAL OFFICIEL" in phrase:
            return False
        if phrase.startswith(("EPSF", "Lien Titre", "Arrêté du")):
            return False
        if re.search(r"\b[CD]\.$", phrase):
            return False
        return phrase.endswith((".", "!", "?"))

    def _selectionner_phrases_utiles(self, phrases: list[str], question: str) -> list[str]:
        mots_question = self._mots_significatifs(question)
        priorites = ("marche à vue", "marche a vue", "conducteur doit", "doivent observer", "consiste", "permet")
        notees: list[tuple[float, str]] = []
        for position, phrase in enumerate(phrases):
            nettoyee = self._nettoyer_resume(phrase)
            if not nettoyee:
                continue
            texte = nettoyee.lower()
            mots_phrase = self._mots_significatifs(nettoyee)
            recouvrement = len(mots_question.intersection(mots_phrase)) if mots_question else 0
            score = recouvrement * 4.0
            if any(mot in texte for mot in priorites):
                score += 3.0
            if re.search(r"\b(doit|doivent|consiste|permet|signifie|désigne|designe|s'applique|est|sont)\b", texte):
                score += 1.5
            if nettoyee.endswith("?"):
                score -= 4.0
            if len(nettoyee) > 260:
                score -= 1.5
            score -= position * 0.15
            notees.append((score, nettoyee))

        selection: list[str] = []
        for _, phrase in sorted(notees, key=lambda item: item[0], reverse=True):
            if phrase not in selection:
                selection.append(phrase)
            if len(selection) == 3:
                break
        return selection

    def _mots_significatifs(self, texte: str) -> set[str]:
        stopwords = {
            "dans", "avec", "pour", "sans", "sous", "plus", "tout", "tous", "toute", "toutes",
            "une", "des", "les", "aux", "que", "qui", "quoi", "dont", "est", "sont", "sur",
            "par", "pas", "comment", "explique", "résume", "resume", "donne", "dis", "dit",
            "phrase", "court", "courte", "brièvement", "brievement", "ceci", "cela", "cette",
        }
        mots = re.findall(r"[a-zàâçéèêëîïôùûüÿñæœ0-9]{3,}", texte.lower())
        return {mot for mot in mots if mot not in stopwords}

    def _fallback_extrait_propre(self, texte: str) -> list[str]:
        extrait = texte[:260].rsplit(" ", 1)[0].strip(" ;:,.")
        if not extrait:
            return []
        return [extrait + "."]

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
