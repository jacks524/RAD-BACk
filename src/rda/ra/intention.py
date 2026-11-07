"""Reconnaissance de l'intention d'une question, pour choisir quoi faire de la photo.

Un technicien qui joint une photo ne veut pas toujours la meme chose. « Quel est le couple de
serrage ? » appelle une recherche documentaire ; « ou est le rotor ? » appelle un reperage sur
l'image. Sans cette distinction, les deux questions declenchent la meme chose et la seconde reste
sans reponse utile.

La detection est volontairement lexicale et etroite. Un faux positif coute cher ici : il lance un
appel au modele de vision, long sur processeur, pour une question qui n'en demandait pas.
"""

from __future__ import annotations

import re

# « ou est le rotor », « montre-moi la boite a bornes », « localise le ventilateur »…
_DEMANDE = re.compile(
    r"^\s*(?:"
    r"o[uù]\s+(?:est|se\s+trouve|sont|se\s+trouvent)|"
    r"montre[- ]?(?:moi)?|"
    r"localise[rz]?|"
    r"rep[èe]re[rz]?|"
    r"situe[rz]?|"
    r"indique[- ]?(?:moi)?|"
    r"entoure[rz]?|"
    r"identifie\s+(?:sur\s+(?:la\s+|cette\s+)?(?:photo|image))"
    r")\s+"
    # L'elision « l' » n'est pas suivie d'espace : elle a sa propre alternative.
    r"(?:(?:le|la|les|un|une|du|des|de\s+la)\s+|l['’]\s*)?"
    r"(?P<cible>.+?)"
    r"\s*(?:sur\s+(?:la\s+|cette\s+)?(?:photo|image))?\s*[?.!]*\s*$",
    re.I,
)

# Une cible d'un seul caractere, ou faite de ponctuation, n'a pas de sens a chercher.
_CIBLE_VALIDE = re.compile(r"[\wÀ-ÿ]{3,}")


def cible_a_localiser(question: str) -> str | None:
    """Retourne le composant a reperer, ou None si la question n'en demande pas.

    Ne dit rien de la presence d'une photo : c'est a l'appelant de verifier qu'il en a une.
    Une question de reperage sans image n'est qu'une question documentaire ordinaire.
    """
    correspondance = _DEMANDE.match(question or "")
    if not correspondance:
        return None

    cible = correspondance.group("cible").strip(" '’\"«»")
    if not _CIBLE_VALIDE.search(cible):
        return None
    # Une cible tres longue est presque toujours une phrase mal decoupee, pas un composant.
    if len(cible) > 60:
        return None
    return cible


# --------------------------------------------------------------------- description

# Demandes explicites de description, francais et anglais.
_DESCRIPTION = re.compile(
    r"^\s*(?:"
    r"qu['’]?\s*est[- ]ce\s+que\s+c['’]?\s*est|"
    r"c['’]?\s*est\s+quoi|"
    r"de\s+quoi\s+s['’]?\s*agit[- ]il|"
    r"d[ée]cri[stz]|"
    r"que\s+(?:vois|voyez)[- ]tu|que\s+voyez[- ]vous|"
    r"explique[sz]?[- ]?(?:moi)?\s+(?:cette\s+|la\s+|l['’])?(?:image|photo)|"
    r"what\s+is\s+(?:this|it)|"
    r"describe|"
    r"what\s+do\s+you\s+see"
    r")\b.*$",
    re.I,
)

# En deca de ce nombre de mots porteurs, une question ne permet aucune recherche utile.
_MOTS_PORTEURS_MIN = 2


def est_demande_description(question: str) -> bool:
    """Vrai si la question appelle une description de l'image plutot qu'une recherche.

    Deux cas. Le premier est explicite : « qu'est-ce que c'est ? », « décris cette photo ».
    Le second est implicite — une question dont il ne reste presque aucun mot porteur une fois
    les mots outils retires ne peut rien trouver dans un manuel. Chercher « c'est quoi » dans
    une documentation technique ne donne rien, et le silence qui en resulte est inutile alors
    qu'une photo est disponible.

    Ne dit rien de la presence d'une photo : sans image, une question vague reste une question
    vague, et l'abstention est alors la bonne reponse.
    """
    nue = (question or "").strip()
    if not nue:
        return False
    if _DESCRIPTION.match(nue):
        return True

    # « Ou est le rotor ? » ne laisse qu'un mot porteur, mais ce n'est pas une demande de
    # description : c'est un reperage, traite ailleurs. On l'ecarte ici plutot que de compter
    # sur l'ordre des branches de l'appelant, qui pourrait changer.
    if cible_a_localiser(nue):
        return False

    from rda.ra.lexical import tokeniser

    # Les mots d'un caractere et les nombres seuls ne portent pas de sens interrogeable.
    porteurs = [m for m in tokeniser(nue) if len(m) > 2 and not m.isdigit()]
    return len(porteurs) < _MOTS_PORTEURS_MIN
