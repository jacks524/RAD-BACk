"""Service d identite de demonstration : sessions, agents, roles et droits."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

from rda.config import obtenir_parametres
from rda.paquetages.identite.schemas import AgentCreationEntree, AgentSortie, ConnexionSortie


CHEMIN_UTILISATEURS_DEMO = Path("/app/identite-demo/utilisateurs.json")
SESSIONS_DEMO: dict[str, AgentSortie] = {}


class ServiceIdentite:
    """Service d'identite minimal; les roles/groupes sont figes a la connexion."""

    def empreinte_jeton(self, jeton: str) -> str:
        return sha256(jeton.encode("utf-8")).hexdigest()

    async def connecter(self, courriel: str, mot_de_passe: str) -> ConnexionSortie:
        p = obtenir_parametres()
        utilisateur = self._trouver_utilisateur(courriel)
        if utilisateur is not None:
            empreinte = self._empreinte_mot_de_passe(courriel, mot_de_passe)
            if utilisateur["empreinte_mdp"] != empreinte:
                raise ValueError("Identifiants incorrects.")
            roles = utilisateur["roles"]
            agent = AgentSortie(
                courriel=utilisateur["courriel"],
                nom=utilisateur["nom"],
                prenom=utilisateur["prenom"],
                matricule=utilisateur.get("matricule", ""),
                poste=utilisateur.get("poste", ""),
                structure=utilisateur.get("structure", ""),
                statut=utilisateur.get("statut", "ACTIF"),
                groupes_resolus=self._groupes_effectifs(utilisateur),
                roles=roles,
                droits=self._droits(utilisateur),
            )
        else:
            roles = ["ADMINISTRATEUR"] if courriel.lower() == "admin@camrail.cm" else ["AGENT"]
            agent = AgentSortie(courriel=courriel, groupes_resolus=["DEMO_SECURITE"], roles=roles)
        expiration = datetime.now(UTC) + timedelta(minutes=p.duree_session_minutes)
        jeton = sha256(f"{courriel}:{expiration.isoformat()}:{p.secret_jwt}".encode()).hexdigest()
        SESSIONS_DEMO[jeton] = agent
        return ConnexionSortie(jeton=jeton, expiration=expiration, agent=agent)

    async def agent_par_jeton_demo(self, jeton: str) -> AgentSortie | None:
        return SESSIONS_DEMO.get(jeton)

    async def profil_demo(self) -> AgentSortie:
        return AgentSortie(courriel="agent.demo@camrail.cm", groupes_resolus=["DEMO_SECURITE"], roles=["AGENT"])

    async def lister_agents_demo(self) -> list[AgentSortie]:
        return [
            AgentSortie(
                courriel=utilisateur["courriel"],
                nom=utilisateur["nom"],
                prenom=utilisateur["prenom"],
                matricule=utilisateur.get("matricule", ""),
                poste=utilisateur.get("poste", ""),
                structure=utilisateur.get("structure", ""),
                statut=utilisateur.get("statut", "ACTIF"),
                groupes_resolus=self._groupes_effectifs(utilisateur),
                roles=utilisateur["roles"],
                droits=self._droits(utilisateur),
            )
            for utilisateur in self._lire_utilisateurs()
        ]

    async def creer_agent_demo(self, entree: AgentCreationEntree) -> AgentSortie:
        utilisateurs = self._lire_utilisateurs()
        courriel = entree.courriel.lower()
        if any(utilisateur["courriel"].lower() == courriel for utilisateur in utilisateurs):
            utilisateurs = [
                utilisateur
                for utilisateur in utilisateurs
                if utilisateur["courriel"].lower() != courriel
            ]
        utilisateurs.append(
            {
                "matricule": entree.matricule,
                "courriel": entree.courriel,
                "nom": entree.nom,
                "prenom": entree.prenom,
                "poste": entree.poste,
                "structure": entree.structure,
                "statut": entree.statut,
                "empreinte_mdp": self._empreinte_mot_de_passe(entree.courriel, entree.mot_de_passe),
                "groupes_poste": entree.groupes_poste,
                "habilitations_exception": entree.habilitations_exception,
                "roles": entree.roles,
            }
        )
        self._ecrire_utilisateurs(utilisateurs)
        return AgentSortie(
            courriel=entree.courriel,
            nom=entree.nom,
            prenom=entree.prenom,
            matricule=entree.matricule,
            poste=entree.poste,
            structure=entree.structure,
            statut=entree.statut,
            groupes_resolus=entree.groupes_poste + [
                str(h.get("groupe", "")) for h in entree.habilitations_exception if h.get("groupe")
            ],
            roles=entree.roles,
            droits=[
                {"groupe": groupe, "origine": "POSTE", "expiration": None}
                for groupe in entree.groupes_poste
            ]
            + [
                {"groupe": h.get("groupe"), "origine": "EXCEPTION", "expiration": h.get("expiration")}
                for h in entree.habilitations_exception
            ],
        )

    async def modifier_agent_demo(self, courriel: str, entree: AgentCreationEntree) -> AgentSortie:
        utilisateurs = [
            utilisateur
            for utilisateur in self._lire_utilisateurs()
            if utilisateur["courriel"].lower() != courriel.lower()
        ]
        self._ecrire_utilisateurs(utilisateurs)
        return await self.creer_agent_demo(entree)

    def _groupes_effectifs(self, utilisateur: dict) -> list[str]:
        groupes = list(utilisateur.get("groupes_poste") or ["DEMO_SECURITE"])
        groupes.extend(
            str(h.get("groupe"))
            for h in utilisateur.get("habilitations_exception", [])
            if h.get("groupe")
        )
        return groupes

    def _droits(self, utilisateur: dict) -> list[dict]:
        return [
            {"groupe": groupe, "origine": "POSTE", "expiration": None}
            for groupe in utilisateur.get("groupes_poste", ["DEMO_SECURITE"])
        ] + [
            {"groupe": h.get("groupe"), "origine": "EXCEPTION", "expiration": h.get("expiration")}
            for h in utilisateur.get("habilitations_exception", [])
        ]

    def _empreinte_mot_de_passe(self, courriel: str, mot_de_passe: str) -> str:
        secret = obtenir_parametres().secret_jwt
        return sha256(f"{courriel.lower()}:{mot_de_passe}:{secret}".encode()).hexdigest()

    def _trouver_utilisateur(self, courriel: str) -> dict | None:
        courriel_normalise = courriel.lower()
        for utilisateur in self._lire_utilisateurs():
            if utilisateur["courriel"].lower() == courriel_normalise:
                return utilisateur
        return None

    def _lire_utilisateurs(self) -> list[dict]:
        if not CHEMIN_UTILISATEURS_DEMO.exists():
            return []
        return json.loads(CHEMIN_UTILISATEURS_DEMO.read_text(encoding="utf-8"))

    def _ecrire_utilisateurs(self, utilisateurs: list[dict]) -> None:
        CHEMIN_UTILISATEURS_DEMO.parent.mkdir(parents=True, exist_ok=True)
        CHEMIN_UTILISATEURS_DEMO.write_text(
            json.dumps(utilisateurs, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
