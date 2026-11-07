"""Test de fumee KALATI : l'application demarre, on se connecte, on pose une question.

La suite existante couvrait la logique unitaire mais ne montait jamais l'application. Ce test
verrouille le contrat HTTP de KALATI, qui est precisement ce que l'ajout du module RA ne doit pas
deplacer : memes chemins, memes codes, memes cles de reponse.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rda.main import creer_application


@pytest.fixture
def client():
    with TestClient(creer_application()) as clientele:
        yield clientele


def test_l_application_demarre_et_repond_sur_health(client):
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "OK"


def test_health_expose_le_module_ra_sans_alterer_le_statut(client):
    """Le module RA s'ajoute sous sa propre cle ; « statut » garde sa valeur d'origine."""
    charge = client.get("/health").json()
    assert charge["statut"] == "OK"
    assert "module_ra" in charge


def test_connexion_rend_un_jeton_et_un_profil(client):
    reponse = client.post(
        "/api/v1/auth/connexion",
        json={"courriel": "agent.demo@camrail.cm", "mot_de_passe": "demo"},
    )
    assert reponse.status_code == 200
    charge = reponse.json()
    assert charge["jeton"]
    assert charge["agent"]["courriel"] == "agent.demo@camrail.cm"
    assert charge["agent"]["groupes_resolus"]


def test_une_question_texte_traverse_la_chaine(client):
    """La route metier historique reste accessible et rend la forme attendue."""
    reponse = client.post(
        "/api/v1/questions",
        json={"question": "Quelles sont les consignes avant le depart d'un train ?"},
    )
    assert reponse.status_code == 200
    charge = reponse.json()
    assert "mode_reponse" in charge or "reponse" in charge


def test_les_routes_ra_exigent_une_authentification(client):
    """Contrairement a POST /questions, les routes du module refusent l'appel anonyme."""
    assert client.get("/api/v1/ra/equipements").status_code == 401


def test_un_jeton_inconnu_est_refuse(client):
    reponse = client.get(
        "/api/v1/ra/equipements", headers={"Authorization": "Bearer jeton-invente"}
    )
    assert reponse.status_code == 401


def test_les_routes_ra_ignorent_l_entete_de_groupes(client):
    """Annoncer ses propres groupes ne doit ouvrir aucun acces : ils viennent de la session."""
    reponse = client.get(
        "/api/v1/ra/equipements", headers={"X-Groupes-Agent": "G_DMAT,G_DIF"}
    )
    assert reponse.status_code == 401


def test_un_jeton_kalati_ouvre_les_routes_ra(client):
    """Meme jeton, meme mecanisme : c'est le contrat annonce a la section 8.2 de la spec."""
    jeton = client.post(
        "/api/v1/auth/connexion",
        json={"courriel": "agent.demo@camrail.cm", "mot_de_passe": "demo"},
    ).json()["jeton"]

    reponse = client.get(
        "/api/v1/ra/equipements", headers={"Authorization": f"Bearer {jeton}"}
    )
    # 200 si les artefacts sont charges, 503 sinon — mais jamais 401 : le jeton est accepte.
    assert reponse.status_code in (200, 503)
