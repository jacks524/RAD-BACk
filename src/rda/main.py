from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rda.commun.erreurs import ErreurRDA, gerer_erreur_rda
from rda.config import obtenir_parametres
from rda.infra.inference import ClientInference
from rda.noyau.agent import AgentRDA
from rda.paquetages.corpus.routes import routeur as routeur_corpus
from rda.paquetages.reponse.artefacts import charger_passages
from rda.paquetages.identite.routes import routeur as routeur_identite
from rda.paquetages.reponse.routes import service_reponse
from rda.paquetages.reponse.routes import routeur as routeur_reponse


async def initialiser_artefacts() -> None:
    """Charge les artefacts si les tables sont vides.

    La phase reelle d'import est portee par les services d'ingestion; ce point garde le demarrage
    idempotent et documente le contrat.
    """
    parametres = obtenir_parametres()
    passages = charger_passages(parametres.artefacts_dir)
    service_reponse.passages_demo = passages


@asynccontextmanager
async def duree_vie(app: FastAPI):
    parametres = obtenir_parametres()
    agent = AgentRDA()
    app.state.agent = agent
    await initialiser_artefacts()
    try:
        await ClientInference(parametres.inference_url).verifier_sante()
    except Exception:
        pass
    agent.demarrer()
    try:
        yield
    finally:
        await agent.arreter()


def creer_application() -> FastAPI:
    parametres = obtenir_parametres()
    app = FastAPI(title="RDA CAMRAIL", version="0.1.0", lifespan=duree_vie)
    app.add_exception_handler(ErreurRDA, gerer_erreur_rda)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=parametres.liste_origines_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routeur_identite, prefix="/api/v1")
    app.include_router(routeur_reponse, prefix="/api/v1")
    app.include_router(routeur_corpus, prefix="/api/v1")

    @app.get("/health")
    async def sante() -> dict:
        return {"statut": "OK"}

    return app


app = creer_application()
