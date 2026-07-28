from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentDocument:
    ordre: int
    chemin_hierarchique: str
    texte: str
    page_debut: int
    page_fin: int


def segmenter_pages(pages: list) -> list[SegmentDocument]:
    segments = []
    for page in pages:
        texte = getattr(page, "texte", "")
        if texte.strip():
            segments.append(
                SegmentDocument(
                    ordre=len(segments) + 1,
                    chemin_hierarchique=f"page/{getattr(page, 'numero', 1)}",
                    texte=texte,
                    page_debut=getattr(page, "numero", 1),
                    page_fin=getattr(page, "numero", 1),
                )
            )
    return segments

