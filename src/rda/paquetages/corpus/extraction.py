from dataclasses import dataclass


@dataclass(frozen=True)
class PageExtraite:
    numero: int
    texte: str
    reference_image: str | None = None


def extraire_pdf(_: bytes) -> list[PageExtraite]:
    """Point d'extension pour pdfplumber/PyMuPDF; ferme par defaut."""

    return []

