from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from rda.paquetages.identite.schemas import (
    AgentCreationEntree,
    AgentSortie,
    ConnexionEntree,
    ConnexionSortie,
    GroupeEntree,
    PosteEntree,
    ProfilSortie,
)
from rda.paquetages.identite.service import ServiceIdentite

routeur = APIRouter(tags=["identite"])


async def exiger_administrateur(authorization: str = Header(default="")) -> None:
    prefixe = "Bearer "
    if not authorization.startswith(prefixe):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise.")

    jeton = authorization.removeprefix(prefixe).strip()
    agent = await ServiceIdentite().agent_par_jeton_demo(jeton)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session inconnue ou expirée.")
    if "ADMINISTRATEUR" not in agent.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé au rôle ADMINISTRATEUR.")


@routeur.post("/auth/connexion", response_model=ConnexionSortie)
async def connecter(entree: ConnexionEntree) -> ConnexionSortie:
    try:
        return await ServiceIdentite().connecter(entree.courriel, entree.mot_de_passe)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@routeur.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def fermer_session() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@routeur.get("/auth/moi", response_model=ProfilSortie)
async def lire_moi() -> ProfilSortie:
    return ProfilSortie(**(await ServiceIdentite().profil_demo()).model_dump())


@routeur.get("/admin/postes", dependencies=[Depends(exiger_administrateur)])
async def lister_postes() -> dict:
    return {"items": []}


@routeur.post("/admin/postes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(exiger_administrateur)])
async def creer_poste(entree: PosteEntree) -> dict:
    return entree.model_dump()


@routeur.get("/admin/groupes", dependencies=[Depends(exiger_administrateur)])
async def lister_groupes() -> dict:
    return {"items": []}


@routeur.post("/admin/groupes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(exiger_administrateur)])
async def creer_groupe(entree: GroupeEntree) -> dict:
    return entree.model_dump()


@routeur.get("/admin/agents", dependencies=[Depends(exiger_administrateur)])
async def lister_agents() -> dict:
    return {"items": await ServiceIdentite().lister_agents_demo()}


@routeur.post("/admin/agents", response_model=AgentSortie, status_code=status.HTTP_201_CREATED, dependencies=[Depends(exiger_administrateur)])
async def creer_agent(entree: AgentCreationEntree) -> AgentSortie:
    return await ServiceIdentite().creer_agent_demo(entree)


@routeur.put("/admin/agents/{courriel}", response_model=AgentSortie, dependencies=[Depends(exiger_administrateur)])
async def modifier_agent(courriel: str, entree: AgentCreationEntree) -> AgentSortie:
    return await ServiceIdentite().modifier_agent_demo(courriel, entree)


@routeur.get("/admin/journal", dependencies=[Depends(exiger_administrateur)])
async def lister_journal() -> dict:
    return {"items": []}
