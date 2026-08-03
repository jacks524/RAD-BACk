"""Module backend RDA consacre a ingestion."""

import asyncio
from collections.abc import Awaitable, Callable

from rda.noyau.fils.base import Fil


class FilIngestion(Fil):
    """Fil sequentiel de versement documentaire."""

    nom = "ingestion"

    def __init__(self, etat, traiter_tache: Callable[[], Awaitable[None]] | None = None):
        super().__init__(etat)
        self.traiter_tache = traiter_tache

    async def executer(self) -> None:
        while self._actif:
            self.etat.battre(self.nom)
            if self.etat.est_sature():
                await asyncio.sleep(1.0)
                continue
            if self.traiter_tache:
                await self.traiter_tache()
            await asyncio.sleep(0.2)


