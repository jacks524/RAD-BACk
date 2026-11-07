"""Journalisation des appels /ra/*, en ajout seul.

Chaque appel laisse une trace portant les habilitations effectivement appliquees. C'est ce qui
rend le cloisonnement auditable apres coup : on peut prouver pourquoi un agent a obtenu, ou n'a
pas obtenu, une source donnee — et non seulement affirmer que le filtre etait pose.

Un echec d'ecriture du journal n'interrompt pas la reponse, mais il est trace en erreur : perdre
une reponse de maintenance parce que la base d'audit est indisponible serait un mauvais arbitrage.
La trace applicative reste alors le dernier recours.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import text

journal_applicatif = logging.getLogger("rda.ra.journal")

INSERTION = text(
    """
    INSERT INTO ra.journal (
      id_entree, ref_agent, action, equipement_id, groupes_resolus, mode, confiance,
      seuil_applique, nb_citations, latence_ms, resultat, adresse_ip, detail
    ) VALUES (
      :id_entree, :ref_agent, :action, :equipement_id, CAST(:groupes_resolus AS jsonb), :mode,
      :confiance, :seuil_applique, :nb_citations, :latence_ms, :resultat, :adresse_ip,
      CAST(:detail AS jsonb)
    )
    """
)


async def enregistrer(
    *,
    action: str,
    agent_courriel: str | None,
    groupes: list[str],
    resultat: str = "SUCCES",
    equipement_id: str | None = None,
    mode: str | None = None,
    confiance: float | None = None,
    seuil: float | None = None,
    nb_citations: int | None = None,
    latence_ms: int | None = None,
    adresse_ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entree au journal du module. N'echoue jamais bruyamment."""
    parametres = {
        "id_entree": str(uuid4()),
        "ref_agent": agent_courriel,
        "action": action,
        "equipement_id": equipement_id,
        "groupes_resolus": json.dumps(sorted(groupes)),
        "mode": mode,
        "confiance": confiance,
        "seuil_applique": seuil,
        "nb_citations": nb_citations,
        "latence_ms": latence_ms,
        "resultat": resultat,
        "adresse_ip": adresse_ip,
        "detail": json.dumps(detail or {}, ensure_ascii=False),
    }

    try:
        from rda.infra.bases import SessionCorpus

        async with SessionCorpus() as session:
            async with session.begin():
                await session.execute(INSERTION, parametres)
    except Exception as erreur:  # noqa: BLE001 — l'audit ne doit pas casser la reponse
        journal_applicatif.error(
            "journal RA non ecrit (%s) — action=%s agent=%s resultat=%s groupes=%s",
            erreur,
            action,
            agent_courriel,
            resultat,
            sorted(groupes),
        )


async def lire(limite: int = 100, agent: str | None = None) -> list[dict[str, Any]]:
    """Dernieres entrees du journal, les plus recentes d'abord."""
    from rda.infra.bases import SessionCorpus

    requete = """
        SELECT id_entree, horodatage, ref_agent, action, equipement_id, mode, confiance,
               seuil_applique, nb_citations, latence_ms, resultat
        FROM ra.journal
        {filtre}
        ORDER BY horodatage DESC
        LIMIT :limite
    """.format(filtre="WHERE ref_agent = :agent" if agent else "")

    parametres: dict[str, Any] = {"limite": limite}
    if agent:
        parametres["agent"] = agent

    async with SessionCorpus() as session:
        lignes = (await session.execute(text(requete), parametres)).mappings().all()
    return [
        {**dict(ligne), "id_entree": str(ligne["id_entree"]), "horodatage": ligne["horodatage"].isoformat()}
        for ligne in lignes
    ]
