import asyncio

from rda.noyau.fils.base import Fil


class FilDialogue(Fil):
    """Pool prioritaire charge des questions utilisateur."""

    nom = "dialogue"

    async def executer(self) -> None:
        while self._actif:
            self.etat.battre(self.nom)
            await asyncio.sleep(0.5)


