from datetime import UTC, datetime, timedelta
from hashlib import sha256

from rda.config import obtenir_parametres
from rda.paquetages.identite.schemas import AgentSortie, ConnexionSortie


class ServiceIdentite:
    """Service d'identite minimal; les roles/groupes sont figes a la connexion."""

    def empreinte_jeton(self, jeton: str) -> str:
        return sha256(jeton.encode("utf-8")).hexdigest()

    async def connecter(self, courriel: str, mot_de_passe: str) -> ConnexionSortie:
        del mot_de_passe
        p = obtenir_parametres()
        expiration = datetime.now(UTC) + timedelta(minutes=p.duree_session_minutes)
        jeton = sha256(f"{courriel}:{expiration.isoformat()}:{p.secret_jwt}".encode()).hexdigest()
        agent = AgentSortie(courriel=courriel, groupes_resolus=["DEMO_SECURITE"], roles=["AGENT"])
        return ConnexionSortie(jeton=jeton, expiration=expiration, agent=agent)

    async def profil_demo(self) -> AgentSortie:
        return AgentSortie(courriel="agent.demo@camrail.cm", groupes_resolus=["DEMO_SECURITE"], roles=["AGENT"])

