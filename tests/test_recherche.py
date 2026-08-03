"""Tests automatises couvrant le comportement test recherche du backend RDA."""

from datetime import date

from rda.paquetages.reponse.recherche import rechercher_hybride_en_memoire


def test_recherche_hybride_conserve_les_trois_scores(passages_normatifs):
    candidats = rechercher_hybride_en_memoire(
        question="depart train frein radio",
        passages=passages_normatifs,
        groupes_resolus=["SECURITE"],
        date_reference=date(2024, 7, 1),
    )

    assert candidats
    assert candidats[0].score_dense >= 0
    assert candidats[0].score_lexical > 0
    assert candidats[0].score_fusion > 0
    assert candidats[0].rang == 1

