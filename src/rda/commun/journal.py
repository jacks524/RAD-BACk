from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from rda.paquetages.identite.modeles import EntreeJournal


async def journaliser(
    session: AsyncSession,
    *,
    action: str,
    resultat: str,
    ref_agent: UUID | None = None,
    entite_cible: str | None = None,
    adresse_ip: str | None = None,
    detail: dict | None = None,
) -> None:
    """Ecrit une entree d'audit en ajout seul."""

    session.add(
        EntreeJournal(
            horodatage=datetime.now(UTC),
            ref_agent=ref_agent,
            action=action,
            entite_cible=entite_cible,
            adresse_ip=adresse_ip,
            resultat=resultat,
            detail=detail or {},
        )
    )

