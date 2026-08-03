"""Module backend RDA consacre a sentinelle."""

import asyncio

from rda.noyau.fils.base import Fil


class FilSentinelle(Fil):
    """Horloge quotidienne de detection d'abrogations et anomalies."""

    nom = "sentinelle"

    async def executer(self) -> None:
        while self._actif:
            self.etat.battre(self.nom)
            await asyncio.sleep(24 * 60 * 60)


