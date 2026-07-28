from dataclasses import dataclass


SEUILS_INITIAUX: dict[str, float] = {
    "SECURITE": 0.72,
    "TRANSPORT": 0.68,
    "RH": 0.55,
    "JURIDIQUE": 0.55,
    "FINANCE": 0.45,
    "COMMERCIAL": 0.40,
    "DEFAUT": 0.60,
}


@dataclass(frozen=True)
class Politique:
    """Politique de deliberation par perimetre metier."""

    seuils_abstention: dict[str, float]
    seuil_generatif: float = 0.80

    @classmethod
    def initiale(cls) -> "Politique":
        return cls(seuils_abstention=SEUILS_INITIAUX.copy())

    def seuil_abstention(self, perimetre: str | None) -> float:
        return self.seuils_abstention.get((perimetre or "DEFAUT").upper(), SEUILS_INITIAUX["DEFAUT"])


