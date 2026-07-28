from datetime import date

import pytest

from rda.paquetages.reponse.recherche import rechercher_hybride_en_memoire


def test_droits_sources_differentes_et_fermeture_sans_session(passages_normatifs):
    question = "Que prevoit la regle pour le depart du train et le frein ?"

    securite = rechercher_hybride_en_memoire(
        question=question,
        passages=passages_normatifs,
        groupes_resolus=["SECURITE"],
        date_reference=date(2024, 7, 1),
    )
    rh = rechercher_hybride_en_memoire(
        question=question,
        passages=passages_normatifs,
        groupes_resolus=["RH"],
        date_reference=date(2024, 7, 1),
    )
    sans_session = rechercher_hybride_en_memoire(
        question=question,
        passages=passages_normatifs,
        groupes_resolus=[],
        date_reference=date(2024, 7, 1),
    )

    assert securite
    assert rh
    assert securite[0].passage.id_passage != rh[0].passage.id_passage
    assert sans_session == []

