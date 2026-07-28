from datetime import date
from uuid import uuid4

import pytest

from rda.paquetages.reponse.recherche import PassageIndexe


@pytest.fixture
def passages_normatifs() -> list[PassageIndexe]:
    doc_securite = uuid4()
    doc_rh = uuid4()
    return [
        PassageIndexe(
            id_passage=uuid4(),
            id_version=uuid4(),
            id_document=doc_securite,
            titre="Reglement securite circulation 2017",
            reference_normative="RSC-2017 art. 12",
            texte="Le depart du train impose un essai de frein complet avant circulation.",
            page=12,
            groupes_autorises=["SECURITE"],
            date_effet=date(2017, 1, 1),
            date_abrogation=date(2020, 1, 1),
            vecteur=[0.9, 0.2, 0.1, 0.4, 0.1, 0.3, 0.2, 0.1],
        ),
        PassageIndexe(
            id_passage=uuid4(),
            id_version=uuid4(),
            id_document=doc_securite,
            titre="Reglement securite circulation 2024",
            reference_normative="RSC-2024 art. 18",
            texte="Le depart du train impose un essai de frein complet et une confirmation radio.",
            page=18,
            groupes_autorises=["SECURITE"],
            date_effet=date(2024, 1, 1),
            date_abrogation=None,
            vecteur=[0.91, 0.19, 0.1, 0.4, 0.1, 0.3, 0.2, 0.1],
        ),
        PassageIndexe(
            id_passage=uuid4(),
            id_version=uuid4(),
            id_document=doc_rh,
            titre="Convention collective",
            reference_normative="CC art. 7",
            texte="Le conge annuel des agents est encadre par la convention collective.",
            page=7,
            groupes_autorises=["RH"],
            date_effet=date(2015, 1, 1),
            date_abrogation=None,
            vecteur=[0.1, 0.8, 0.2, 0.3, 0.5, 0.1, 0.2, 0.2],
        ),
    ]

