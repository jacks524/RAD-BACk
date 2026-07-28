from abc import ABC, abstractmethod
from asyncio import Task, create_task

from rda.noyau.etat import EtatInterne


class Fil(ABC):
    """Classe abstraite commune aux fils de l'agent."""

    nom = "fil"

    def __init__(self, etat: EtatInterne):
        self.etat = etat
        self._tache: Task | None = None
        self._actif = False

    def demarrer(self) -> Task:
        self._actif = True
        self._tache = create_task(self.executer(), name=self.nom)
        return self._tache

    async def arreter(self) -> None:
        self._actif = False
        if self._tache:
            self._tache.cancel()

    @abstractmethod
    async def executer(self) -> None:
        """Execute la boucle du fil."""


