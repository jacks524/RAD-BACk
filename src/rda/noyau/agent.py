from rda.noyau.etat import EtatInterne
from rda.noyau.fils.dialogue import FilDialogue
from rda.noyau.fils.ingestion import FilIngestion
from rda.noyau.fils.sentinelle import FilSentinelle
from rda.noyau.politique import Politique


class AgentRDA:
    """Application-agent portant les trois fils concurrents."""

    def __init__(self, politique: Politique | None = None):
        self.etat = EtatInterne()
        self.politique = politique or Politique.initiale()
        self.fils = [
            FilDialogue(self.etat),
            FilIngestion(self.etat),
            FilSentinelle(self.etat),
        ]

    def demarrer(self) -> None:
        for fil in self.fils:
            fil.demarrer()

    async def arreter(self) -> None:
        for fil in self.fils:
            await fil.arreter()

