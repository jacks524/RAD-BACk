from rda.paquetages.reponse.recherche import vecteur_question


def calculer_plongement(texte: str, dimensions: int = 768) -> list[float]:
    """Delegue normalement au service d'inference; implementation deterministe pour tests."""

    base = vecteur_question(texte, min(dimensions, 8))
    return (base * ((dimensions // len(base)) + 1))[:dimensions]


def construire_index_lexical(texte: str) -> str:
    return " ".join(sorted(set(texte.lower().split())))

