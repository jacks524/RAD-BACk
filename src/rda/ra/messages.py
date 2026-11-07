"""Messages que le systeme produit lui-meme, dans la langue de la question.

La regle est simple : **la reponse est dans la langue de la question**, quelle que soit la langue
du document d'ou elle sort. Un technicien qui demande en francais lit en francais.

Ce module ne couvre que les phrases dont le systeme est l'auteur — accueil, refus, abstention.
Le texte d'un extrait de manuel, lui, reste dans la langue du manuel : il est restitue mot pour
mot, et le traduire sans modele reviendrait a le reecrire.
"""

from __future__ import annotations

LANGUES = ("fr", "en")
DEFAUT = "fr"

_MESSAGES: dict[str, dict[str, str]] = {
    "fr": {
        "neutralisation": "Requête refusée : instruction détectée dans la question.",
        "accueil": "Bonjour. Posez votre question sur l'équipement : procédure, pièce, valeur, schéma.",
        "aucun_document": "Aucun document accessible ne traite de ce sujet pour cet équipement.",
        "abstention": "Cette information n'est pas couverte par les documents auxquels vous avez accès.",
        "documents_proches": "Documents les plus proches",
        "extrait_autre_langue": "Extrait du manuel en anglais, seule version disponible pour ce point",
        "non_repere": "n'a pas été repéré sur votre photo",
    },
    "en": {
        "neutralisation": "Request refused: an instruction was detected in the question.",
        "accueil": "Hello. Ask your question about the equipment: procedure, part, value, diagram.",
        "aucun_document": "No accessible document covers this subject for this equipment.",
        "abstention": "This information is not covered by the documents you have access to.",
        "documents_proches": "Closest documents",
        "extrait_autre_langue": "Excerpt from the French manual, the only version available on this point",
        "non_repere": "was not located on your photo",
    },
}


def message(cle: str, langue: str | None = None) -> str:
    """Retourne le message dans la langue demandee, ou dans celle du deploiement."""
    table = _MESSAGES.get(langue or DEFAUT) or _MESSAGES[DEFAUT]
    return table.get(cle) or _MESSAGES[DEFAUT].get(cle, "")


def mention_langue_source(langue_question: str, langue_source: str | None) -> str | None:
    """Avertissement a afficher quand l'extrait n'est pas dans la langue de la question.

    On ne masque pas le fait : un technicien francophone a qui on sert de l'anglais doit savoir
    pourquoi, et qu'il ne s'agit pas d'une erreur mais de la seule version existante.
    """
    if not langue_source or langue_source == langue_question:
        return None
    autre = "en" if langue_source == "en" else "fr"
    cle = "extrait_autre_langue"
    table = _MESSAGES.get(langue_question) or _MESSAGES[DEFAUT]
    texte = table[cle]
    # Le libelle de chaque langue nomme l'autre : on le corrige si la source est du francais.
    if langue_question == "fr" and autre == "fr":
        texte = texte.replace("anglais", "français")
    if langue_question == "en" and autre == "en":
        texte = texte.replace("French", "English")
    return texte
