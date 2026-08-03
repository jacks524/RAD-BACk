"""Module backend RDA consacre a redaction."""

from rda.config import obtenir_parametres
from rda.commun.types import ModeReponse
from rda.paquetages.reponse.reclassement import PassageReclasse


def rediger_abstention(proches: list[PassageReclasse]) -> str:
    titres = []
    for proche in proches[:3]:
        titre = proche.candidat.passage.titre
        if titre not in titres:
            titres.append(titre)
    suffixe = f" Documents les plus proches: {', '.join(titres)}." if titres else ""
    return obtenir_parametres().message_abstention + suffixe


def rediger_extractif(retenus: list[PassageReclasse]) -> str:
    if not retenus:
        return obtenir_parametres().message_abstention
    passage = retenus[0].candidat.passage
    return f"{passage.texte}\n\nSource: [1] {passage.reference_normative}, page {passage.page}."


def rediger_generatif(retenus: list[PassageReclasse]) -> str:
    phrases = []
    for rang, retenu in enumerate(retenus[:3], start=1):
        extrait = retenu.candidat.passage.texte.strip()
        phrases.append(f"{extrait} [{rang}]")
    return " ".join(phrases)


def rediger(mode: ModeReponse, retenus: list[PassageReclasse]) -> str:
    if mode == ModeReponse.ABSTENTION:
        return rediger_abstention(retenus)
    if mode == ModeReponse.EXTRACTIF:
        return rediger_extractif(retenus)
    return rediger_generatif(retenus)

