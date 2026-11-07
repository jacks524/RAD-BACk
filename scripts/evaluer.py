#!/usr/bin/env python3
"""Rejoue le jeu d'evaluation et produit le tableau de recette.

    python scripts/evaluer.py --dossier /ra-data/artefacts [--n 30]

Les chiffres de reference viennent d'un GPU Kaggle. Sur CPU, les latences seront tres
superieures : ce sont les mesures de qualite — citation, abstention, hallucination — qui doivent
se retrouver, pas le temps.

Trois mesures meritent qu'on s'arrete sur leur definition :

  taux_citation     part des reponses non abstenues qui citent au moins une source. Une reponse
                    affirmative sans citation est un defaut bloquant, pas une imperfection.
  abstention_juste  part des questions hors corpus ou le systeme s'est effectivement taire. Se
                    taire quand on ne sait pas est une reussite, pas un echec.
  hallucination     part des questions hors corpus ou le systeme a repondu quand meme. Doit
                    valoir zero ; toute valeur non nulle invalide la recette.

Specification : docs/spec-module-ra.md, section 9.3.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rda.ra.agent import AgentRA  # noqa: E402
from rda.ra.artefacts import ArtefactInvalide, charger  # noqa: E402
from rda.ra.clients import ClientEncodeurs, ClientVision, ServiceIndisponible  # noqa: E402
from rda.ra.deliberation import MODE_ABSTENTION, MODE_NEUTRALISATION  # noqa: E402
from rda.ra.etat import EtatRA  # noqa: E402
from rda.ra.identification import identifier  # noqa: E402

MODES_SANS_REPONSE = {MODE_ABSTENTION, MODE_NEUTRALISATION}


def _dire(message: str = "") -> None:
    print(message, flush=True)


async def evaluer_bout_en_bout(
    moteur: AgentRA, jeu: list[dict[str, Any]], hors_corpus: list[str], groupes: list[str]
) -> dict[str, Any]:
    """Rejoue les questions du jeu, puis les questions hors corpus."""
    detail: list[dict[str, Any]] = []
    repondues = citees = source_juste = 0
    latences: list[float] = []

    for cas in jeu:
        try:
            resultat = await moteur.repondre(
                cas["q"], groupes=groupes, equipement=cas.get("equipement")
            )
        except ServiceIndisponible as erreur:
            _dire(f"  service indisponible : {erreur.detail} — évaluation interrompue")
            raise

        latences.append(resultat["latence_s"])
        mode = resultat["mode"]
        citations = resultat.get("citations") or []

        if mode not in MODES_SANS_REPONSE:
            repondues += 1
            if citations:
                citees += 1
            if any(c["id"] == cas["id_attendu"] for c in citations):
                source_juste += 1

        detail.append(
            {
                "question": cas["q"],
                "nature": cas.get("nature"),
                "mode": mode,
                "confiance": resultat.get("confiance"),
                "latence_s": resultat["latence_s"],
                "source_juste": any(c["id"] == cas["id_attendu"] for c in citations),
            }
        )

    # Questions hors corpus : la bonne reponse est le silence.
    silences = 0
    for question in hors_corpus:
        resultat = await moteur.repondre(question, groupes=groupes)
        latences.append(resultat["latence_s"])
        tu = resultat["mode"] in MODES_SANS_REPONSE
        silences += int(tu)
        detail.append(
            {
                "question": question,
                "nature": "hors_corpus",
                "mode": resultat["mode"],
                "confiance": resultat.get("confiance"),
                "latence_s": resultat["latence_s"],
                "source_juste": None,
            }
        )

    nombre = len(jeu) or 1
    nombre_hors = len(hors_corpus) or 1
    latences_triees = sorted(latences)
    indice_p95 = max(0, int(len(latences_triees) * 0.95) - 1)

    return {
        "taux_reponse": repondues / nombre,
        "taux_citation": (citees / repondues) if repondues else 0.0,
        "source_juste": source_juste / nombre,
        "abstention_juste": silences / nombre_hors,
        "hallucination": (nombre_hors - silences) / nombre_hors,
        "latence_moyenne_s": statistics.mean(latences) if latences else 0.0,
        "latence_p95_s": latences_triees[indice_p95] if latences_triees else 0.0,
        "detail": detail,
    }


async def evaluer_identification(etat: EtatRA, moteur: AgentRA, groupes: list[str]) -> dict:
    """Identification en leave-one-out : chaque photo sans elle-meme dans l'index.

    Sans exclusion, chaque photo se reconnaitrait a la perfection et la mesure ne dirait rien.
    """
    photos = [
        etat.elements[position]
        for position in etat.positions_visuelles
        if etat.elements[position]["type"] == "PHOTO"
    ]
    if not photos:
        return {"photos_testees": 0, "decisions": 0, "exactes": 0}

    dossier = etat.dossier
    decisions = exactes = 0
    for photo in photos:
        fichier = dossier / photo["chemin_image"]
        if not fichier.is_file():
            continue
        vecteur = (await moteur.encodeurs.encoder_visuel_image([fichier.read_bytes()]))[0]
        import numpy as np

        resultat = identifier(
            np.asarray(vecteur, dtype=np.float32),
            vecteurs_image=etat.vecteurs_image,
            positions_visuelles=etat.positions_visuelles,
            elements=etat.elements,
            equipements=etat.equipements,
            seuil=float(etat.politique["seuil_identification"]),
            marge=float(etat.politique["marge_identification"]),
            groupes=groupes,
            exclure=[photo["chemin_image"]],
        )
        if resultat.get("confiant"):
            decisions += 1
            exactes += int(resultat.get("equipement_id") == photo["equipement_id"])

    return {
        "photos_testees": len(photos),
        "decisions": decisions,
        "exactes": exactes,
        "exactitude": (exactes / decisions) if decisions else 0.0,
        "couverture": decisions / len(photos),
    }


def afficher(mesures: dict[str, Any], reference: dict[str, Any] | None) -> None:
    lignes = [
        ("taux de réponse", "taux_reponse", "{:.3f}"),
        ("taux de citation", "taux_citation", "{:.3f}"),
        ("source juste", "source_juste", "{:.3f}"),
        ("abstention juste", "abstention_juste", "{:.3f}"),
        ("hallucination", "hallucination", "{:.3f}"),
        ("latence moyenne (s)", "latence_moyenne_s", "{:.2f}"),
        ("latence p95 (s)", "latence_p95_s", "{:.2f}"),
    ]
    largeur = max(len(libelle) for libelle, _, _ in lignes)
    _dire()
    _dire(f"{'mesure'.ljust(largeur)}   obtenu   référence   écart")
    _dire("-" * (largeur + 30))
    for libelle, cle, format_ in lignes:
        obtenu = mesures[cle]
        if reference and cle in reference:
            attendu = reference[cle]
            ecart = obtenu - attendu
            _dire(
                f"{libelle.ljust(largeur)}   {format_.format(obtenu):>6}   "
                f"{format_.format(attendu):>9}   {ecart:+.3f}"
            )
        else:
            _dire(f"{libelle.ljust(largeur)}   {format_.format(obtenu):>6}   {'—':>9}")


async def executer(arguments: argparse.Namespace) -> int:
    try:
        artefacts = charger(arguments.dossier)
    except ArtefactInvalide as erreur:
        _dire(f"ARTEFACT REFUSÉ : {erreur}")
        return 1

    etat = EtatRA()
    etat.construire(artefacts)
    moteur = AgentRA(
        etat,
        ClientEncodeurs(arguments.url_encodeurs, delai=arguments.delai_encodeurs),
        ClientVision(arguments.url_vision, delai=arguments.delai_vision),
    )

    jeu_complet = artefacts.modeles and json.loads(
        (arguments.dossier / "jeu_evaluation.json").read_text(encoding="utf-8")
    )
    jeu = (jeu_complet.get("eval_auto") or [])[: arguments.n]
    hors_corpus = jeu_complet.get("hors_corpus") or []
    groupes = sorted({e["groupe"] for e in artefacts.elements})

    _dire(f"jeu : {len(jeu)} questions + {len(hors_corpus)} hors corpus · groupes {groupes}")
    _dire("évaluation en cours — plusieurs dizaines de secondes par question avec image sur CPU…")

    mesures = await evaluer_bout_en_bout(moteur, jeu, hors_corpus, groupes)

    reference = None
    fichier_reference = arguments.dossier / "resultats_evaluation.json"
    if fichier_reference.is_file():
        reference = json.loads(fichier_reference.read_text(encoding="utf-8")).get("bout_en_bout")

    afficher(mesures, reference)

    if not arguments.sans_identification:
        _dire("\nidentification en leave-one-out…")
        identification = await evaluer_identification(etat, moteur, groupes)
        _dire(
            f"  {identification['photos_testees']} photos · "
            f"{identification['decisions']} décisions · "
            f"exactitude {identification.get('exactitude', 0):.3f} · "
            f"couverture {identification.get('couverture', 0):.3f}"
        )
        mesures["identification"] = identification

    if mesures["hallucination"] > 0:
        _dire(
            f"\nRECETTE EN ÉCHEC : {mesures['hallucination']:.1%} des questions hors corpus ont "
            "obtenu une réponse. L'indicateur doit valoir zéro."
        )

    if arguments.sortie:
        arguments.sortie.write_text(
            json.dumps(mesures, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        _dire(f"\nrésultats écrits dans {arguments.sortie}")

    return 0 if mesures["hallucination"] == 0 else 3


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--dossier", required=True, type=Path)
    analyseur.add_argument("--n", type=int, default=30, help="nombre de questions rejouées")
    analyseur.add_argument("--url-encodeurs", default=None)
    analyseur.add_argument("--url-vision", default=None)
    analyseur.add_argument("--delai-encodeurs", type=float, default=600.0)
    analyseur.add_argument("--delai-vision", type=float, default=900.0)
    analyseur.add_argument("--sortie", type=Path, default=None)
    analyseur.add_argument("--sans-identification", action="store_true")
    return asyncio.run(executer(analyseur.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
