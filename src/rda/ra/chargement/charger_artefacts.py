"""Chargement des artefacts vers le schema « ra », avec controle de coherence de l'encodeur.

    python -m rda.ra.chargement.charger_artefacts --dossier /ra-data/artefacts

Le controle de coherence est la raison d'etre de cette commande. « modeles.json » declare quel
encodeur a produit l'index, mais une declaration ne se verifie pas : on reencode un echantillon
avec l'encodeur reellement en service et on compare au vecteur stocke. Si les cosinus s'ecartent,
l'index et les requetes ne vivent pas dans le meme espace, et tous les scores denses sont faux
sans que rien ne le signale. Le chargement echoue alors franchement.

Specification : docs/spec-module-ra.md, sections 3.2 et 3.3.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from sqlalchemy import text

from rda.ra.artefacts import ArtefactInvalide, Artefacts, charger
from rda.ra.clients import ClientEncodeurs, ServiceIndisponible

SEUIL_COSINUS = 0.99
TAILLE_ECHANTILLON = 32
GRAINE = 42
PREFIXE_INDEX = "passage"


def _dire(message: str) -> None:
    print(message, flush=True)


# --------------------------------------------------------------------- controle de coherence


async def controler_encodeur(
    artefacts: Artefacts, encodeurs: ClientEncodeurs, *, taille: int = TAILLE_ECHANTILLON
) -> dict[str, Any]:
    """Reencode un echantillon et compare aux vecteurs stockes.

    L'echantillon est tire avec une graine fixe : deux executations sur les memes artefacts
    donnent le meme verdict, ce qui rend le controle reproductible en recette.
    """
    nombre = len(artefacts.elements)
    generateur = np.random.default_rng(GRAINE)
    positions = generateur.choice(nombre, size=min(taille, nombre), replace=False)

    textes = [artefacts.elements[int(i)]["texte"] for i in positions]
    vecteurs = np.asarray(await encodeurs.encoder_texte(textes, PREFIXE_INDEX), dtype=np.float32)
    stockes = artefacts.vecteurs_texte[positions]

    cosinus = np.einsum("ij,ij->i", vecteurs, stockes)
    return {
        "taille_echantillon": int(len(positions)),
        "cosinus_min": float(cosinus.min()),
        "cosinus_median": float(np.median(cosinus)),
        "part_conforme": float((cosinus >= SEUIL_COSINUS).mean()),
        "reussi": bool(np.all(cosinus >= SEUIL_COSINUS)),
    }


# --------------------------------------------------------------------- ecriture en base


def _date(valeur: Any) -> "date | None":
    """Convertit une date ISO du parquet en objet date.

    Les artefacts portent les dates en chaine ; les colonnes sont de type « date ». asyncpg
    ne fait pas la conversion et rejette la chaine telle quelle.
    """
    if not valeur:
        return None
    if isinstance(valeur, date):
        return valeur
    try:
        return date.fromisoformat(str(valeur)[:10])
    except ValueError:
        return None


def _vecteur_pg(vecteur: np.ndarray | None) -> str | None:
    """Litteral pgvector : « [0.1,0.2,...] »."""
    if vecteur is None:
        return None
    return "[" + ",".join(f"{float(v):.7g}" for v in vecteur) + "]"


async def ecrire(artefacts: Artefacts, controle: dict[str, Any], encodeur_texte: str) -> None:
    """Remplace le contenu du schema « ra » par ces artefacts, en une transaction."""
    from rda.infra.bases import SessionCorpusIngestion

    positions_visuelles = artefacts.positions_visuelles
    rang_visuel = {position: rang for rang, position in enumerate(positions_visuelles)}

    async with SessionCorpusIngestion() as session:
        async with session.begin():
            # Remplacement complet : un chargement partiel laisserait un index incoherent avec
            # les matrices reconstruites en memoire.
            await session.execute(text("DELETE FROM ra.elements"))
            await session.execute(text("DELETE FROM ra.equipements"))

            for equipement in artefacts.equipements:
                await session.execute(
                    text(
                        """
                        INSERT INTO ra.equipements
                          (equipement_id, nom, direction, famille, groupe, constructeur, modele,
                           fiche_presente)
                        VALUES (:id, :nom, :direction, :famille, :groupe, :constructeur, :modele,
                                :fiche)
                        ON CONFLICT (equipement_id) DO UPDATE SET nom = EXCLUDED.nom
                        """
                    ),
                    {
                        "id": equipement["id"],
                        "nom": equipement["nom"],
                        "direction": equipement["direction"],
                        "famille": equipement["famille"],
                        "groupe": equipement["groupe"],
                        "constructeur": equipement.get("constructeur"),
                        "modele": equipement.get("modele"),
                        "fiche": bool(equipement.get("fiche_presente", False)),
                    },
                )

            insertion = text(
                """
                INSERT INTO ra.elements (
                  id, equipement_id, equipement_nom, famille, direction, groupe, cle_doc,
                  titre_doc, type_doc, indice, date_effet, date_abrogation, chemin_hierarchique,
                  page_debut, page_fin, type, texte, reference, texte_ocr, chemin_image,
                  description_json, vecteur_texte, vecteur_image, ordre
                ) VALUES (
                  :id, :equipement_id, :equipement_nom, :famille, :direction, :groupe, :cle_doc,
                  :titre_doc, :type_doc, :indice, :date_effet, :date_abrogation,
                  :chemin_hierarchique, :page_debut, :page_fin, :type, :texte, :reference,
                  :texte_ocr, :chemin_image, CAST(:description_json AS jsonb),
                  CAST(:vecteur_texte AS vector), CAST(:vecteur_image AS vector), :ordre
                )
                """
            )

            for ordre, element in enumerate(artefacts.elements):
                vecteur_image = None
                if ordre in rang_visuel:
                    vecteur_image = artefacts.vecteurs_image[rang_visuel[ordre]]
                await session.execute(
                    insertion,
                    {
                        **element,
                        "date_effet": _date(element["date_effet"]),
                        "date_abrogation": _date(element["date_abrogation"]),
                        "vecteur_texte": _vecteur_pg(artefacts.vecteurs_texte[ordre]),
                        "vecteur_image": _vecteur_pg(vecteur_image),
                        "ordre": ordre,
                    },
                )

            politique = artefacts.politique
            await session.execute(
                text(
                    """
                    INSERT INTO ra.politique (
                      numero_version, seuils_abstention, seuil_generatif, k_recuperation, k_final,
                      rrf_k, poids_canaux, max_images_reponse, seuil_identification,
                      marge_identification, vlm_max_pixels_reponse, phrase_abstention,
                      prompt_systeme, prompt_description, date_activation
                    ) VALUES (
                      :numero_version, CAST(:seuils AS jsonb), :seuil_generatif, :k_recuperation,
                      :k_final, :rrf_k, CAST(:poids AS jsonb), :max_images,
                      :seuil_identification, :marge_identification, :vlm_max_pixels,
                      :phrase, :systeme, :description, :date_activation
                    )
                    ON CONFLICT (numero_version) DO NOTHING
                    """
                ),
                {
                    "numero_version": politique["numero_version"],
                    "seuils": json.dumps(politique["seuils_abstention"]),
                    "seuil_generatif": politique["seuil_generatif"],
                    "k_recuperation": politique["k_recuperation"],
                    "k_final": politique["k_final"],
                    "rrf_k": politique["rrf_k"],
                    "poids": json.dumps(politique["poids_canaux"]),
                    "max_images": politique["max_images_reponse"],
                    "seuil_identification": politique["seuil_identification"],
                    "marge_identification": politique["marge_identification"],
                    "vlm_max_pixels": politique["vlm_max_pixels_reponse"],
                    "phrase": politique["phrase_abstention"],
                    "systeme": politique["prompt_systeme"],
                    "description": politique["prompt_description"],
                    "date_activation": _date(politique["date_activation"]),
                },
            )

            await session.execute(text("DELETE FROM ra.glossaire"))
            for terme, synonymes in artefacts.glossaire.items():
                await session.execute(
                    text(
                        "INSERT INTO ra.glossaire (terme, synonymes) "
                        "VALUES (:terme, CAST(:synonymes AS jsonb))"
                    ),
                    {"terme": terme, "synonymes": json.dumps(synonymes, ensure_ascii=False)},
                )

            await session.execute(
                text(
                    """
                    INSERT INTO ra.chargements (
                      id_chargement, version_artefacts, empreinte, encodeur_texte, encodeur_visuel,
                      cosinus_median, controle_reussi, nb_elements, nb_visuels, detail
                    ) VALUES (
                      :id, :version, :empreinte, :encodeur_texte, :encodeur_visuel, :cosinus,
                      :reussi, :nb_elements, :nb_visuels, CAST(:detail AS jsonb)
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "version": artefacts.modeles.get("date_export", "inconnue"),
                    "empreinte": artefacts.empreinte,
                    "encodeur_texte": encodeur_texte,
                    "encodeur_visuel": artefacts.modeles.get("encodeur_visuel", "inconnu"),
                    "cosinus": controle.get("cosinus_median"),
                    "reussi": controle.get("reussi", False),
                    "nb_elements": len(artefacts.elements),
                    "nb_visuels": len(positions_visuelles),
                    "detail": json.dumps(controle),
                },
            )


# --------------------------------------------------------------------- commande


async def executer(arguments: argparse.Namespace) -> int:
    _dire(f"lecture des artefacts : {arguments.dossier}")
    try:
        artefacts = charger(arguments.dossier)
    except ArtefactInvalide as erreur:
        _dire(f"ARTEFACT REFUSÉ : {erreur}")
        return 1

    _dire(
        f"  {len(artefacts.elements)} éléments · {len(artefacts.positions_visuelles)} visuels · "
        f"{len(artefacts.equipements)} équipement(s) · contrat respecté"
    )
    _dire(f"  encodeur déclaré : {artefacts.modeles.get('encodeur_texte')}")

    # Delai propre au chargement : une requete encode une chaine courte, ce controle encode
    # un lot de passages entiers sur processeur. Reutiliser le delai des requetes le ferait
    # echouer systematiquement.
    encodeurs = ClientEncodeurs(arguments.url_encodeurs, delai=arguments.delai)
    _dire(f"contrôle de cohérence sur {arguments.echantillon} éléments…")
    try:
        controle = await controler_encodeur(artefacts, encodeurs, taille=arguments.echantillon)
    except ServiceIndisponible as erreur:
        _dire(f"ÉCHEC : ra-encodeurs injoignable — {erreur.detail}")
        return 1

    _dire(
        f"  cosinus médian {controle['cosinus_median']:.4f} · min {controle['cosinus_min']:.4f} · "
        f"conformes {controle['part_conforme']:.1%}"
    )

    if not controle["reussi"]:
        _dire(
            f"\nÉCHEC DU CONTRÔLE DE COHÉRENCE.\n"
            f"L'encodeur en service ne reproduit pas l'index : {controle['part_conforme']:.1%} des "
            f"cosinus atteignent {SEUIL_COSINUS}, le minimum observé est "
            f"{controle['cosinus_min']:.4f}.\n"
            f"L'index a été produit par « {artefacts.modeles.get('encodeur_texte')} ».\n"
            f"Deux issues : fournir ces poids à ra-encodeurs, ou réexporter l'index avec "
            f"l'encodeur en service (scripts/reexporter_index_texte.py)."
        )
        if not arguments.forcer:
            return 2
        _dire("--forcer : chargement poursuivi malgré l'incohérence. Scores denses non fiables.")

    if arguments.controle_seul:
        _dire("--controle-seul : rien n'a été écrit.")
        return 0 if controle["reussi"] else 2

    modeles_sante = await encodeurs.sante()
    encodeur_texte = modeles_sante.get("modeles", {}).get("texte", "inconnu")

    _dire("écriture dans le schéma ra…")
    await ecrire(artefacts, controle, encodeur_texte)
    _dire(f"chargement terminé · empreinte {artefacts.empreinte[:16]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--dossier", required=True, type=Path)
    analyseur.add_argument("--url-encodeurs", default=None)
    analyseur.add_argument("--echantillon", type=int, default=TAILLE_ECHANTILLON)
    analyseur.add_argument(
        "--delai", type=float, default=600.0, help="delai d'attente des encodeurs, secondes"
    )
    analyseur.add_argument(
        "--controle-seul", action="store_true", help="vérifier sans rien écrire"
    )
    analyseur.add_argument(
        "--forcer", action="store_true", help="charger malgré un contrôle en échec"
    )
    return asyncio.run(executer(analyseur.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
