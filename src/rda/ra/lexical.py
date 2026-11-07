"""Normalisation du texte, tokenisation et index lexical BM25.

Portage fidele des cellules 15 et 22 du notebook. La tokenisation doit reproduire exactement celle
de l'indexation : une divergence ici deplace silencieusement les scores du canal lexical.
"""

from __future__ import annotations

import re
import unicodedata

# Mots vides francais et anglais, repris tels quels du notebook (cellule 22).
MOTS_VIDES: frozenset[str] = frozenset(
    "le la les de des du un une et ou a au aux en dans pour par sur avec est sont "
    "the of and to in for on is are".split()
)

_MOTS = re.compile(r"\w+", re.UNICODE)


def sans_accents(texte: str) -> str:
    """Retire les diacritiques (cellule 6)."""
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def tokeniser(texte: str) -> list[str]:
    """Minuscules, accents retires, mots, puis retrait des mots vides (cellule 22)."""
    return [m for m in _MOTS.findall(sans_accents(texte.lower())) if m not in MOTS_VIDES]


class IndexLexical:
    """Index BM25 Okapi reconstruit en memoire au demarrage et apres chaque chargement."""

    def __init__(self, textes: list[str]):
        from rank_bm25 import BM25Okapi

        self._taille = len(textes)
        # Un corpus vide fait echouer BM25Okapi ; on garde l'objet utilisable et neutre.
        self._bm25 = BM25Okapi([tokeniser(t) for t in textes]) if textes else None

    def __len__(self) -> int:
        return self._taille

    def scores(self, question: str):
        """Scores BM25 de la question contre tout le corpus, dans l'ordre des elements."""
        import numpy as np

        if self._bm25 is None:
            return np.zeros(self._taille, dtype=np.float64)
        return np.asarray(self._bm25.get_scores(tokeniser(question)))
