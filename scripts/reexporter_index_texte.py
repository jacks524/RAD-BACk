#!/usr/bin/env python3
"""Reexporte l'index texte des artefacts avec l'encodeur de base.

Pourquoi ce script existe. Les artefacts livres declarent dans « modeles.json » un encodeur
affine (« encodeur_affine (base intfloat/multilingual-e5-base) ») dont les poids n'ont jamais ete
livres. Le controle de coherence du chargeur (cosinus >= 0,99) echoue donc, et c'est son role :
interroger un index avec un modele different de celui qui l'a produit donne des scores denses
silencieusement faux.

Ce script reencode les 599 elements avec l'encodeur de base, via le service « ra-encodeurs » —
celui-la meme qui encodera les requetes a l'execution. La coherence est donc vraie par
construction, et non verifiee apres coup.

L'index visuel n'est pas touche : SigLIP2 n'a pas ete affine.

    python scripts/reexporter_index_texte.py --dossier /ra-data/artefacts
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

PREFIXE_INDEX = "passage"
SEUIL_COSINUS = 0.99
LOT = 64


def _journaliser(message: str) -> None:
    print(message, flush=True)


def encoder_par_lots(url: str, textes: list[str], delai: float) -> tuple[np.ndarray, str]:
    """Encode les textes par lots. Retourne les vecteurs et le nom du modele employe."""
    vecteurs: list[list[float]] = []
    modele = ""
    with httpx.Client(timeout=delai) as client:
        for debut in range(0, len(textes), LOT):
            lot = textes[debut : debut + LOT]
            reponse = client.post(
                f"{url.rstrip('/')}/encoder/texte",
                json={"textes": lot, "prefixe": PREFIXE_INDEX},
            )
            reponse.raise_for_status()
            charge = reponse.json()
            vecteurs.extend(charge["vecteurs"])
            modele = charge["modele"]
            _journaliser(f"  encodes {min(debut + LOT, len(textes)):5d} / {len(textes)}")
    return np.asarray(vecteurs, dtype=np.float32), modele


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--dossier", required=True, type=Path, help="dossier des artefacts")
    analyseur.add_argument(
        "--url", default="http://localhost:8082", help="URL du service ra-encodeurs"
    )
    analyseur.add_argument("--delai", type=float, default=600.0, help="delai d'attente, secondes")
    analyseur.add_argument(
        "--sans-sauvegarde", action="store_true", help="ne pas conserver l'index precedent"
    )
    arguments = analyseur.parse_args()

    dossier: Path = arguments.dossier
    chemin_elements = dossier / "elements.parquet"
    chemin_vecteurs = dossier / "embeddings_texte.npy"
    chemin_modeles = dossier / "modeles.json"

    for chemin in (chemin_elements, chemin_vecteurs, chemin_modeles):
        if not chemin.exists():
            _journaliser(f"ERREUR : fichier absent — {chemin}")
            return 1

    elements = pd.read_parquet(chemin_elements)
    anciens = np.load(chemin_vecteurs)
    _journaliser(f"elements : {len(elements)} · index actuel : {anciens.shape}")

    if anciens.shape[0] != len(elements):
        _journaliser(
            f"ERREUR : l'index actuel ({anciens.shape[0]}) ne correspond pas aux elements "
            f"({len(elements)}). Artefacts incoherents, reexport interrompu."
        )
        return 1

    textes = [str(t) if t is not None else "" for t in elements["texte"].tolist()]

    _journaliser(f"reencodage via {arguments.url} (prefixe « {PREFIXE_INDEX}: »)")
    try:
        nouveaux, modele = encoder_par_lots(arguments.url, textes, arguments.delai)
    except httpx.HTTPError as erreur:
        _journaliser(f"ERREUR : service ra-encodeurs injoignable ou en echec — {erreur}")
        return 1

    if nouveaux.shape != anciens.shape:
        _journaliser(f"ERREUR : dimensions inattendues {nouveaux.shape}, attendu {anciens.shape}")
        return 1

    normes = np.linalg.norm(nouveaux, axis=1)
    if not np.all((normes > 0.99) & (normes < 1.01)):
        _journaliser(f"ERREUR : vecteurs non normes (norme min {normes.min():.4f})")
        return 1

    # Ecart avec l'index precedent : mesure ce que l'affinage apportait, et confirme que les deux
    # index sont bien differents (sinon le controle de coherence aurait deja reussi).
    cosinus = np.einsum("ij,ij->i", nouveaux, anciens)
    _journaliser(
        f"ecart avec l'index precedent — cosinus median {np.median(cosinus):.4f} · "
        f"min {cosinus.min():.4f} · part >= {SEUIL_COSINUS} : "
        f"{float((cosinus >= SEUIL_COSINUS).mean()):.1%}"
    )

    if not arguments.sans_sauvegarde:
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        for chemin in (chemin_vecteurs, chemin_modeles):
            sauvegarde = chemin.with_suffix(f"{chemin.suffix}.avant-reexport-{horodatage}")
            shutil.copy2(chemin, sauvegarde)
            _journaliser(f"sauvegarde : {sauvegarde.name}")

    np.save(chemin_vecteurs, nouveaux)

    modeles = json.loads(chemin_modeles.read_text(encoding="utf-8"))
    modeles["encodeur_texte"] = modele
    modeles["dimensions_texte"] = int(nouveaux.shape[1])
    modeles["encodeur_texte_origine"] = "reexport local, encodeur de base"
    modeles["date_reexport_texte"] = datetime.now().isoformat(timespec="seconds")
    chemin_modeles.write_text(
        json.dumps(modeles, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    _journaliser(
        f"\nindex reexporte : {nouveaux.shape} · encodeur « {modele} »\n"
        "le controle de coherence du chargeur reussit desormais par construction."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
