from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def poser_groupes_transaction(session: AsyncSession, groupes_resolus: list[str]) -> None:
    """Pose le parametre RLS obligatoire pour la transaction courante."""

    await session.execute(
        text("SET LOCAL app.groupes_agent = :groupes"),
        {"groupes": ",".join(sorted(groupes_resolus))},
    )


def groupes_depuis_session(session_donnees: dict) -> list[str]:
    groupes = session_donnees.get("groupes_resolus", [])
    if isinstance(groupes, dict):
        groupes = groupes.get("groupes", [])
    return [str(g) for g in groupes]


def verifier_acces_logique(ref_groupe: UUID | str, groupes_resolus: list[str]) -> bool:
    return str(ref_groupe) in {str(g) for g in groupes_resolus}

