"""Chargement des artefacts Kaggle en passages exploitables par le backend."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np
import pandas as pd

from rda.paquetages.reponse.recherche import PassageIndexe


def charger_passages(artefacts_dir: Path) -> list[PassageIndexe]:
    passages_path = artefacts_dir / "passages.parquet"
    embeddings_path = artefacts_dir / "embeddings.npy"
    if not passages_path.exists() or not embeddings_path.exists():
        return []

    table = pd.read_parquet(passages_path)
    embeddings = np.load(embeddings_path)
    passages: list[PassageIndexe] = []

    for position, (_, row) in enumerate(table.iterrows()):
        vecteur = embeddings[position].astype(float).tolist() if position < len(embeddings) else []
        texte = str(_valeur(row, ["texte", "contenu", "passage", "extrait", "text"], ""))
        reference = str(
            _valeur(row, ["reference_normative", "reference", "ref", "article", "source"], "Source")
        )
        titre = str(_valeur(row, ["titre", "document", "nom_document", "fichier"], reference))
        passages.append(
            PassageIndexe(
                id_passage=_uuid(_valeur(row, ["id_passage", "passage_id"], f"passage:{position}")),
                id_version=_uuid(_valeur(row, ["id_version", "version_id"], f"version:{titre}")),
                id_document=_uuid(_valeur(row, ["id_document", "document_id"], f"document:{titre}")),
                titre=titre,
                reference_normative=reference,
                texte=texte,
                page=int(_valeur(row, ["page", "numero_page"], 1) or 1),
                groupes_autorises=_groupes(
                    _valeur(
                        row,
                        ["groupes_autorises", "groupes", "habilitations", "perimetres"],
                        ["DEMO_SECURITE", "SECURITE"],
                    )
                ),
                date_effet=_date(_valeur(row, ["date_effet", "date_debut", "date"], None), date(1900, 1, 1)),
                date_abrogation=_date(_valeur(row, ["date_abrogation", "date_fin"], None), None),
                vecteur=vecteur,
            )
        )

    return [passage for passage in passages if passage.texte.strip()]


def _valeur(row: pd.Series, noms: list[str], defaut: Any) -> Any:
    colonnes = {str(colonne).lower(): colonne for colonne in row.index}
    for nom in noms:
        colonne = colonnes.get(nom.lower())
        if colonne is not None and _present(row[colonne]):
            return row[colonne]
    return defaut


def _present(valeur: Any) -> bool:
    if valeur is None:
        return False
    if isinstance(valeur, (list, tuple, set, np.ndarray)):
        return len(valeur) > 0
    return bool(pd.notna(valeur))


def _uuid(valeur: Any) -> UUID:
    texte = str(valeur)
    try:
        return UUID(texte)
    except ValueError:
        return uuid5(NAMESPACE_URL, texte)


def _date(valeur: Any, defaut: date | None) -> date | None:
    if valeur is None or pd.isna(valeur):
        return defaut
    if isinstance(valeur, date):
        return valeur
    return pd.to_datetime(valeur).date()


def _groupes(valeur: Any) -> list[str]:
    if valeur is None:
        return ["DEMO_SECURITE", "SECURITE"]
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return ["DEMO_SECURITE", "SECURITE"]
        try:
            valeur = json.loads(texte)
        except json.JSONDecodeError:
            return [g.strip() for g in texte.split(",") if g.strip()]
    if isinstance(valeur, (list, tuple, set, np.ndarray)):
        groupes = [str(g).strip() for g in valeur if str(g).strip()]
        return groupes or ["DEMO_SECURITE", "SECURITE"]
    return [str(valeur)]
