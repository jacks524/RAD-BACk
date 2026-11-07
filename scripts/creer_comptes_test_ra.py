#!/usr/bin/env python3
"""Cree les comptes de test du module RA dans le referentiel d'identite.

    python scripts/creer_comptes_test_ra.py [--fichier chemin/utilisateurs.json]

Les mots de passe viennent de .env (RDA_RA_MDP_*) et ne sont jamais ecrits dans le code ni
affiches. Le script est idempotent : relance-le, il remplace les comptes existants de meme
adresse sans toucher aux autres.

Deux reserves, qui tiennent a KALATI et non au module RA (voir docs/spec-module-ra.md 8.4) :
l'empreinte de mot de passe est un SHA-256 non sale, et les sessions vivent en memoire. Ces
comptes sont des comptes de demonstration ; ils n'ont pas vocation a exister en production.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rda.config import obtenir_parametres  # noqa: E402
from rda.ra.config import obtenir_parametres_ra  # noqa: E402

CHEMIN_DEFAUT = Path("/app/identite-demo/utilisateurs.json")

COMPTES = [
    {
        "courriel": "technicien.dmat@test",
        "nom": "Technicien",
        "prenom": "DMAT",
        "matricule": "T-DMAT-001",
        "poste": "TECHNICIEN_MATERIEL",
        "structure": "DMAT",
        "groupes_poste": ["G_DMAT"],
        "roles": ["AGENT"],
        "cle_mdp": "mdp_technicien_dmat",
    },
    {
        "courriel": "technicien.dif@test",
        "nom": "Technicien",
        "prenom": "DIF",
        "matricule": "T-DIF-001",
        "poste": "TECHNICIEN_INSTALLATIONS",
        "structure": "DIF",
        "groupes_poste": ["G_DIF"],
        "roles": ["AGENT"],
        "cle_mdp": "mdp_technicien_dif",
    },
    {
        "courriel": "securite@test",
        "nom": "Agent",
        "prenom": "Sécurité",
        "matricule": "S-001",
        "poste": "AGENT_SECURITE",
        "structure": "CI",
        "groupes_poste": ["G_DMAT", "G_DIF"],
        "roles": ["AGENT"],
        "cle_mdp": "mdp_securite",
    },
]


def empreinte(courriel: str, mot_de_passe: str, secret: str) -> str:
    """Meme calcul que ServiceIdentite._empreinte_mot_de_passe."""
    return sha256(f"{courriel.lower()}:{mot_de_passe}:{secret}".encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--fichier", type=Path, default=CHEMIN_DEFAUT)
    arguments = analyseur.parse_args(argv)

    secret = obtenir_parametres().secret_jwt
    parametres_ra = obtenir_parametres_ra()

    manquants = [c["courriel"] for c in COMPTES if not getattr(parametres_ra, c["cle_mdp"], "")]
    if manquants:
        print(
            "ERREUR : mots de passe absents de .env pour " + ", ".join(manquants) + ".\n"
            "Renseigne RDA_RA_MDP_TECHNICIEN_DMAT, RDA_RA_MDP_TECHNICIEN_DIF et "
            "RDA_RA_MDP_SECURITE.",
            file=sys.stderr,
        )
        return 1

    fichier: Path = arguments.fichier
    fichier.parent.mkdir(parents=True, exist_ok=True)
    existants = json.loads(fichier.read_text(encoding="utf-8")) if fichier.is_file() else []

    adresses = {c["courriel"].lower() for c in COMPTES}
    conserves = [u for u in existants if u.get("courriel", "").lower() not in adresses]

    maintenant = datetime.now(UTC).isoformat()
    for modele in COMPTES:
        mot_de_passe = getattr(parametres_ra, modele["cle_mdp"])
        conserves.append(
            {
                "matricule": modele["matricule"],
                "courriel": modele["courriel"],
                "nom": modele["nom"],
                "prenom": modele["prenom"],
                "poste": modele["poste"],
                "structure": modele["structure"],
                "statut": "ACTIF",
                "empreinte_mdp": empreinte(modele["courriel"], mot_de_passe, secret),
                "groupes_poste": modele["groupes_poste"],
                "habilitations_exception": [],
                "roles": modele["roles"],
                "date_creation": maintenant,
            }
        )

    fichier.write_text(json.dumps(conserves, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(COMPTES)} comptes de test écrits dans {fichier}")
    for modele in COMPTES:
        print(f"  {modele['courriel']:26s} -> {', '.join(modele['groupes_poste'])}")
    print(
        f"\n{len(conserves) - len(COMPTES)} compte(s) préexistant(s) conservé(s).\n"
        "Les mots de passe sont ceux de .env ; ils ne sont pas affichés ici."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
