"""Point d entree FastAPI : assemble les routeurs, charge les artefacts et demarre les services de fond."""

import logging
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
from rda.ra.config import obtenir_parametres_ra
from rda.ra.etat import etat_ra
from rda.ra.routes import routeur as routeur_ra

journal = logging.getLogger("rda")


async def initialiser_artefacts() -> None:
    """Charge les artefacts si les tables sont vides.

    La phase reelle d'import est portee par les services d'ingestion; ce point garde le demarrage
    idempotent et documente le contrat.
    """
    parametres = obtenir_parametres()
    passages = charger_passages(parametres.artefacts_dir)
    service_reponse.passages_demo = passages


async def initialiser_module_ra() -> None:
    """Charge les artefacts du module RA et reconstruit son index lexical.

    Un echec n'empeche pas le demarrage : KALATI doit rester disponible meme si le module RA ne
    l'est pas. Les routes /ra/* repondent alors 503, et /health le signale.
    """
    parametres = obtenir_parametres_ra()
    if not parametres.actif:
        journal.info("module RA desactive (RDA_RA_ACTIF)")
        return
    try:
        etat_ra.charger_depuis(parametres.artefacts_dir)
    except Exception as erreur:  # noqa: BLE001 — le module RA est optionnel au demarrage
        journal.warning("module RA non charge : %s", erreur)


@asynccontextmanager
async def duree_vie(app: FastAPI):
    parametres = obtenir_parametres()
    agent = AgentRDA()
    app.state.agent = agent
    await initialiser_artefacts()
    await initialiser_module_ra()
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
    app.include_router(routeur_ra, prefix="/api/v1")

    @app.get("/health")
    async def sante() -> dict:
        """Etat de KALATI, etendu a l'etat du module RA.

        Le contrat de KALATI est preserve : « statut » reste en tete et garde sa valeur. Le
        module RA s'ajoute sous sa propre cle, et son indisponibilite ne degrade pas le statut
        global — les deux piles peuvent tourner l'une sans l'autre.
        """
        from rda.ra.clients import ClientEncodeurs, ClientVision

        parametres_ra = obtenir_parametres_ra()
        module_ra: dict = {"actif": parametres_ra.actif, "artefacts_charges": etat_ra.charge}

        if parametres_ra.actif:
            if etat_ra.charge:
                module_ra.update(
                    nb_elements=len(etat_ra.elements),
                    nb_visuels=len(etat_ra.positions_visuelles),
                    nb_equipements=len(etat_ra.equipements),
                    version_artefacts=etat_ra.artefacts.empreinte[:16],
                    encodeur_texte=etat_ra.encodeur_texte,
                    politique_version=etat_ra.politique.get("numero_version"),
                )
            module_ra["ra_vision"] = await ClientVision().sante()
            module_ra["ra_encodeurs"] = await ClientEncodeurs().sante()

        return {"statut": "OK", "module_ra": module_ra}

    return app


app = creer_application()
