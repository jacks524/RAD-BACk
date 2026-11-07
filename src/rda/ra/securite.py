"""Authentification et habilitations des routes /ra/*.

Le module reutilise le jeton de KALATI et son service d'identite, sans les modifier. La dependance
est propre au module : « obtenir_groupes_demo », qui ouvre les routes KALATI, n'est pas touchee.

Difference assumee avec KALATI : aucune route /ra/* n'accepte d'en-tete « X-Groupes-Agent ». Les
habilitations viennent de la session et d'elle seule. Laisser le client annoncer ses propres
groupes reviendrait a le laisser choisir ses droits, ce qui viderait le cloisonnement de son sens.

Specification : docs/spec-module-ra.md, section 8.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from rda.paquetages.identite.service import ServiceIdentite

PREFIXE = "Bearer "
ROLE_ADMINISTRATEUR = "ADMINISTRATEUR"


@dataclass(frozen=True)
class AgentRA:
    """Identite resolue d'un appelant des routes /ra/*."""

    courriel: str
    groupes: list[str]
    roles: list[str]

    @property
    def est_administrateur(self) -> bool:
        return ROLE_ADMINISTRATEUR in self.roles


async def agent_courant(authorization: str = Header(default="")) -> AgentRA:
    """Resout le jeton porteur en identite, ou refuse l'appel.

    Meme extraction et meme registre de sessions que « exiger_administrateur » de KALATI : un
    jeton obtenu par POST /auth/connexion ouvre les routes du module.
    """
    if not authorization.startswith(PREFIXE):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise."
        )

    jeton = authorization.removeprefix(PREFIXE).strip()
    agent = await ServiceIdentite().agent_par_jeton_demo(jeton)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session inconnue ou expirée."
        )

    groupes = [str(g) for g in (agent.groupes_resolus or [])]
    if not groupes:
        # Un agent sans habilitation ne verrait rien ; le dire clairement vaut mieux que de
        # laisser toutes ses recherches revenir vides sans explication.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aucune habilitation n'est attachée à ce compte.",
        )

    return AgentRA(courriel=agent.courriel, groupes=groupes, roles=list(agent.roles or []))


async def exiger_administrateur_ra(agent: AgentRA = Depends(agent_courant)) -> AgentRA:
    """Restreint une route au role ADMINISTRATEUR."""
    if not agent.est_administrateur:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au rôle ADMINISTRATEUR.",
        )
    return agent


def verifier_acces_element(element: dict, agent: AgentRA) -> None:
    """Refuse l'acces a un element hors du perimetre de l'agent.

    Utilise par les routes d'acces direct (images, documents), la ou le filtre de la recherche
    ne s'applique pas.
    """
    if element.get("groupe") not in set(agent.groupes):
        # 404 et non 403 : repondre « interdit » confirmerait l'existence de la ressource, et
        # permettrait de cartographier le corpus d'un autre perimetre par simple sondage.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ressource introuvable.")
