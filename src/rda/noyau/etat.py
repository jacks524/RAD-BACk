from dataclasses import dataclass, field
from time import monotonic


@dataclass
class EtatInterne:
    """Etat partage entre les fils de l'agent."""

    dialogues_en_cours: int = 0
    latence_dialogue_ms: float = 0.0
    limite_dialogues: int = 16
    limite_latence_ms: float = 4500.0
    dernier_battement: dict[str, float] = field(default_factory=dict)

    def est_sature(self) -> bool:
        return (
            self.dialogues_en_cours >= self.limite_dialogues
            or self.latence_dialogue_ms >= self.limite_latence_ms
        )

    def battre(self, nom_fil: str) -> None:
        self.dernier_battement[nom_fil] = monotonic()


