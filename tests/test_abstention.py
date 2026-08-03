"""Tests automatises couvrant le comportement test abstention du backend RDA."""

import pytest

from rda.commun.types import ModeReponse
from rda.paquetages.reponse.service import ServiceReponse


@pytest.mark.asyncio
async def test_hors_corpus_abstention_http_nominale(passages_normatifs):
    service = ServiceReponse(passages_demo=passages_normatifs)

    reponse = await service.repondre(
        question="Quelle est la procedure de peinture des bureaux administratifs ?",
        groupes_resolus=["SECURITE"],
    )

    assert reponse.mode == ModeReponse.ABSTENTION
    assert "pas couverte de façon certaine" in reponse.reponse
    assert reponse.citations == []


@pytest.mark.asyncio
async def test_aucun_generatif_sans_citation(passages_normatifs):
    service = ServiceReponse(passages_demo=passages_normatifs)

    reponse = await service.repondre(
        question="Que prevoit la securite pour le depart du train et le frein ?",
        groupes_resolus=["SECURITE"],
    )

    assert reponse.mode != ModeReponse.GENERATIF or len(reponse.citations) > 0

