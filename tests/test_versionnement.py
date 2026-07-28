from datetime import date

from rda.paquetages.reponse.recherche import rechercher_hybride_en_memoire


def test_question_datee_cite_la_version_en_vigueur(passages_normatifs):
    question = "essai de frein avant depart du train"

    en_2017 = rechercher_hybride_en_memoire(
        question=question,
        passages=passages_normatifs,
        groupes_resolus=["SECURITE"],
        date_reference=date(2017, 6, 1),
    )
    en_2024 = rechercher_hybride_en_memoire(
        question=question,
        passages=passages_normatifs,
        groupes_resolus=["SECURITE"],
        date_reference=date(2024, 6, 1),
    )

    assert en_2017[0].passage.reference_normative == "RSC-2017 art. 12"
    assert en_2024[0].passage.reference_normative == "RSC-2024 art. 18"
    assert all(c.passage.reference_normative != "RSC-2017 art. 12" for c in en_2024)

