"""Rendre un extrait de manuel lisible par un technicien.

Deux problemes distincts, tous deux visibles dans les artefacts livres.

1. Le texte extrait des PDF charrie l'habillage de la page : adresse du site, numero et titre
   courant, et le bandeau vertical capte a l'envers par l'OCR (« SIAÇNARF » pour « FRANÇAIS »).
   Restitue tel quel, cela noie la reponse.

2. Un element fait souvent plusieurs milliers de caracteres. En restituer les 900 premiers donne
   le debut de la section, pas ce qui repond a la question. Le passage utile est ailleurs.

On nettoie, puis on choisit la fenetre de phrases la plus proche de la question. Aucun modele
n'intervient : le resultat est deterministe et se rejoue a l'identique.
"""

from __future__ import annotations

import re

from rda.ra.lexical import tokeniser

# Habillage de page, observe sur les manuels WEG.
_BRUIT = (
    re.compile(r"^\s*(https?://)?www\.[\w.-]+\s*$", re.I),          # www.weg.net
    re.compile(r"^\s*\d+\s+Manuel\b.*$", re.I),                      # « 6 Manuel des Moteurs… »
    re.compile(r"^\s*Manuel des Moteurs [ÉE]lectriques\s*$", re.I),  # titre courant seul
    re.compile(r"^\s*\d{1,4}\s*$"),                                  # numero de page isole
    re.compile(r"^\s*\[page_texte\]\s*", re.I),                      # marqueur d'extraction
)

# Bandeau vertical capte a l'envers : un seul mot, tout en capitales, sans espace.
_BANDEAU = re.compile(r"^\s*[A-ZÀ-ÜÇ]{5,16}\s*$")

_FIN_PHRASE = re.compile(r"(?<=[.!?:;])\s+|\n")


def nettoyer(texte: str) -> str:
    """Retire l'habillage de page, en conservant l'ordre et le contenu utile."""
    lignes = []
    for ligne in (texte or "").splitlines():
        if any(motif.match(ligne) for motif in _BRUIT):
            continue
        if _BANDEAU.match(ligne):
            continue
        if _est_bruit(ligne):
            continue
        lignes.append(ligne.rstrip())

    # Lignes vides consecutives ramenees a une seule.
    propre = re.sub(r"\n{3,}", "\n\n", "\n".join(lignes))
    return propre.strip()


def _fragment_orphelin(phrase: str) -> bool:
    """Vrai si la phrase commence au milieu d'un mot ou d'une proposition.

    L'extraction PDF coupe les elements a la limite des pages, sans egard pour les phrases :
    un element peut donc s'ouvrir sur « ct WEG. » ou « re appliques. ». Restitue tel quel, ce
    fragment n'apporte rien et donne l'impression d'une reponse cassee.
    """
    nue = phrase.strip()
    if not nue or len(nue) > 40:
        return False
    premier = nue[0]
    # Une phrase authentique commence par une majuscule, un chiffre ou une puce.
    return premier.islower() or premier in "'\u2019"


def extraire_pertinent(texte: str, question: str, *, max_caracteres: int = 700) -> str:
    """Renvoie la fenetre de phrases la plus proche de la question.

    Le score d'une phrase est le nombre de termes de la question qu'elle contient. On retient la
    fenetre contigue la mieux notee qui tienne dans la limite : contigue, parce qu'une consigne de
    maintenance perd son sens si on en recolle des morceaux epars.
    """
    propre = nettoyer(texte)
    if len(propre) <= max_caracteres:
        return propre

    phrases = [p.strip() for p in _FIN_PHRASE.split(propre) if p.strip()]
    if not phrases:
        return propre[:max_caracteres].strip()

    termes = set(tokeniser(question))
    if not termes:
        return propre[:max_caracteres].strip()

    scores = [len(termes & set(tokeniser(p))) for p in phrases]

    meilleur_score, meilleur_debut, meilleure_fin = -1, 0, 1
    for debut in range(len(phrases)):
        total, longueur = 0, 0
        for fin in range(debut, len(phrases)):
            longueur += len(phrases[fin]) + 1
            if longueur > max_caracteres:
                break
            total += scores[fin]
            # A score egal, la fenetre la plus large gagne : plus de contexte pour le technicien.
            if total > meilleur_score or (total == meilleur_score and fin - debut > meilleure_fin - meilleur_debut):
                meilleur_score, meilleur_debut, meilleure_fin = total, debut, fin + 1

    retenues = phrases[meilleur_debut:meilleure_fin]
    # Le decoupage en pages laisse parfois un debut de mot orphelin en tete d'element
    # (« ct WEG. » pour « ...contact WEG. »). Servir ce fragment fait croire a un bug.
    while len(retenues) > 1 and _fragment_orphelin(retenues[0]):
        retenues = retenues[1:]
        meilleur_debut += 1

    extrait = " ".join(retenues).strip()
    # Signaler qu'on a coupe : le technicien doit savoir qu'il manque du texte avant ou apres.
    if meilleur_debut > 0:
        extrait = "… " + extrait
    if meilleure_fin < len(phrases):
        extrait = extrait + " …"
    return extrait


# --------------------------------------------------------------------- bruit d'extraction

# Glyphes non resolus par l'extracteur PDF.
_CID = re.compile(r"\(cid:\d+\)")
_MOT = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
# « libelle : valeur · libelle : valeur », forme produite par la serialisation des tableaux.
_LIGNE_TABLEAU = re.compile(r"^[^:]{1,40}\s:\s.+(?:\s·\s[^:]{1,40}\s:\s.+)*$")


def _est_bruit(ligne: str) -> bool:
    """Vrai si la ligne est un residu d'extraction plutot que du texte.

    Les manuels contiennent des schemas de cablage et des tableaux de correspondance que
    l'extracteur a aplatis en suites de caracteres isoles — « LL 1 1 1 1 7 1 4 7 1 4 » sur des
    lignes entieres. C'est illisible pour un humain, et cela occupe la place de la reponse.
    """
    nue = ligne.strip()
    if len(nue) < 12:
        return False
    if _CID.search(nue):
        return True
    # Ligne de tableau serialisee par la chaine d'extraction (« oC : -29 · Ω : 88.617 ») :
    # majoritairement numerique mais parfaitement structuree, donc lisible et souvent decisive
    # — c'est la qu'on lit une valeur de couple ou une resistance.
    if _LIGNE_TABLEAU.match(nue):
        return False

    jetons = nue.split()
    if len(jetons) >= 8:
        # Une suite de jetons d'un ou deux caracteres est un schema aplati, pas une phrase.
        courts = sum(1 for j in jetons if len(j) <= 2)
        if courts / len(jetons) > 0.7:
            return True
        # Tres peu de jetons distincts : repetition mecanique.
        if len(set(jetons)) / len(jetons) < 0.3:
            return True

    # Presque aucun mot reel : soupe de chiffres et de lettres isolees.
    lettres = sum(1 for c in nue if c.isalpha())
    if lettres / len(nue) < 0.3 and len(_MOT.findall(nue)) < 2:
        return True
    return False


def part_lisible(texte: str) -> float:
    """Part des lignes qui ressemblent a du texte, entre 0 et 1.

    Sert a ecarter du premier rang un element qui n'est qu'un residu d'extraction : il peut etre
    pertinent pour la recherche — les chiffres d'un tableau y figurent — sans etre restituable.
    """
    lignes = [l for l in (texte or "").splitlines() if l.strip()]
    if not lignes:
        return 0.0
    return sum(0 if _est_bruit(l) else 1 for l in lignes) / len(lignes)


# --------------------------------------------------------------------- langue

# Mots outils tres frequents, propres a chaque langue et absents ou rares dans l'autre. On evite
# les mots communs (« installation », « position », « type »…) qui ne discriminent rien.
_MOTS_FR = frozenset(
    "le la les des une aux dans pour par sur avec est sont doit doivent etre ete cette ces "
    "ainsi lors selon afin entre sans sous vers chez ou et il elle nous vous leur leurs "
    "peut peuvent faut lorsque apres avant toujours jamais tres plus moins".split()
)
_MOTS_EN = frozenset(
    "the of and to in for on is are must should be been this these thus when according "
    "between without under towards it they we you their can may shall after before always "
    "never very more less with from which that have has".split()
)

# En deca de cet ecart, le texte est trop court ou trop technique pour trancher.
_ECART_MINIMAL = 3


def langue_probable(texte: str) -> str | None:
    """Devine « fr » ou « en », ou None si le texte ne permet pas de trancher.

    Le corpus contient le meme manuel constructeur dans les deux langues. Sans cette distinction,
    une question posee en francais peut se voir citer la version anglaise — exacte, mais
    inexploitable par un technicien qui ne lit pas l'anglais.

    On compte des mots outils plutot que d'appeler une bibliotheque : le vocabulaire technique est
    quasi identique dans les deux versions, ce sont les mots de liaison qui different.
    """
    mots = [m for m in re.findall(r"[a-zà-ÿ]+", (texte or "").lower()) if len(m) > 1]
    if not mots:
        return None

    # Les accents tranchent a eux seuls : l'anglais technique n'en porte pas.
    accents = sum(1 for c in (texte or "") if c in "àâäéèêëîïôöùûüç")

    score_fr = sum(1 for m in mots if m in _MOTS_FR) + min(accents, 10)
    score_en = sum(1 for m in mots if m in _MOTS_EN)

    if abs(score_fr - score_en) < _ECART_MINIMAL:
        return None
    return "fr" if score_fr > score_en else "en"
