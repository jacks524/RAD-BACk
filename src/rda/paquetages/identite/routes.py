from fastapi import APIRouter, Response, status

from rda.paquetages.identite.schemas import ConnexionEntree, ConnexionSortie, GroupeEntree, PosteEntree, ProfilSortie
from rda.paquetages.identite.service import ServiceIdentite

routeur = APIRouter(tags=["identite"])


@routeur.post("/auth/connexion", response_model=ConnexionSortie)
async def connecter(entree: ConnexionEntree) -> ConnexionSortie:
    return await ServiceIdentite().connecter(entree.courriel, entree.mot_de_passe)


@routeur.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def fermer_session() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@routeur.get("/auth/moi", response_model=ProfilSortie)
async def lire_moi() -> ProfilSortie:
    return ProfilSortie(**(await ServiceIdentite().profil_demo()).model_dump())


@routeur.get("/admin/postes")
async def lister_postes() -> dict:
    return {"items": []}


@routeur.post("/admin/postes", status_code=status.HTTP_201_CREATED)
async def creer_poste(entree: PosteEntree) -> dict:
    return entree.model_dump()


@routeur.get("/admin/groupes")
async def lister_groupes() -> dict:
    return {"items": []}


@routeur.post("/admin/groupes", status_code=status.HTTP_201_CREATED)
async def creer_groupe(entree: GroupeEntree) -> dict:
    return entree.model_dump()


@routeur.get("/admin/agents")
async def lister_agents() -> dict:
    return {"items": []}


@routeur.get("/admin/journal")
async def lister_journal() -> dict:
    return {"items": []}

