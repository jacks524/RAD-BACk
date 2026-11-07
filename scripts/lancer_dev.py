#!/usr/bin/env python3
"""Demarre l'API hors conteneur, pour developper le front sans monter toute la pile.

    python scripts/lancer_dev.py [--port 8000] [--artefacts /chemin/vers/artefacts]

Ce lanceur ne modifie aucun fichier de KALATI. Il redirige seulement, au moment du demarrage,
deux chemins codes en dur pour le conteneur :

  - « /app/identite-demo/utilisateurs.json », ou ServiceIdentite lit les comptes ;
  - le dossier d'artefacts du module RA.

Les deux devraient etre configurables par variable d'environnement ; c'est inscrit dans la liste
« demandes au backend » du front. En attendant, cette redirection evite de toucher au code
existant pour une commodite de developpement.

Les bases ne sont pas requises : l'authentification de demonstration lit un fichier, et le module
RA travaille en memoire. Seule la journalisation dans « ra.journal » echouera, en trace d'erreur
et sans interrompre les reponses — ce qui est le comportement prevu.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--port", type=int, default=8000)
    analyseur.add_argument("--hote", default="0.0.0.0")
    analyseur.add_argument(
        "--artefacts", type=Path, default=Path("/mnt/kalati/RDA/rda-data/artefacts")
    )
    analyseur.add_argument(
        "--identites",
        type=Path,
        default=RACINE / "donnees-dev" / "utilisateurs.json",
        help="fichier des comptes de demonstration",
    )
    analyseur.add_argument(
        "--depot", type=Path, default=RACINE / "donnees-dev" / "depot"
    )
    arguments = analyseur.parse_args()

    import os

    os.environ.setdefault("RDA_RA_ARTEFACTS_DIR", str(arguments.artefacts))
    os.environ.setdefault("RDA_RA_DEPOT_DIR", str(arguments.depot))
    arguments.identites.parent.mkdir(parents=True, exist_ok=True)
    arguments.depot.mkdir(parents=True, exist_ok=True)

    # La redirection doit precede toute lecture du module : on importe, on remplace, on demarre.
    from rda.paquetages.identite import service as service_identite

    service_identite.CHEMIN_UTILISATEURS_DEMO = arguments.identites

    from rda.ra.config import obtenir_parametres_ra

    obtenir_parametres_ra.cache_clear()

    print(f"artefacts   : {arguments.artefacts}")
    print(f"identités   : {arguments.identites}")
    print(f"dépôt       : {arguments.depot}")
    print(f"écoute      : http://{arguments.hote}:{arguments.port}")

    import uvicorn

    uvicorn.run(
        "rda.main:creer_application",
        factory=True,
        host=arguments.hote,
        port=arguments.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
