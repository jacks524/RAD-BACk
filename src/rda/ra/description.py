"""Description d'une photo, quand la question ne porte sur rien de documentaire.

« Qu'est-ce que c'est ? » avec une photo n'a pas de reponse dans les manuels : la recherche ne
trouve rien, la confiance s'effondre, et le systeme se tait. C'est logique et c'est inutile — il
lui suffirait de dire ce qu'il voit.

Ce module emprunte au notebook son « prompt_description » (politique.json), ecrit pour indexer les
images du corpus hors ligne. Il en garde la structure et surtout sa consigne : n'inventer rien,
omettre ce qui n'est pas lisible. Seul le rendu change — le technicien lit des phrases, pas du JSON.

**Une description n'est pas une reponse documentaire.** Elle ne cite aucune source et n'engage que
ce que le modele croit voir. L'appelant doit la presenter comme telle, jamais comme une consigne
de maintenance.
"""

from __future__ import annotations

import json
import re
from typing import Any

_OBJET_JSON = re.compile(r"\{.*\}", re.S)
_VIRGULE_TRAINANTE = re.compile(r",\s*([}\]])")

_LANGUE = {
    "fr": {
        "consigne": "Réponds UNIQUEMENT par un objet JSON valide, en français",
        "sans_source": "Description de votre photo par le modèle — aucune source documentaire",
        "composants": "Composants visibles",
        "reperes": "Repères",
        "valeurs": "Valeurs lisibles",
        "anomalies": "Anomalies apparentes",
        "echec": "Je ne parviens pas à décrire cette image de façon fiable.",
    },
    "en": {
        "consigne": "Answer ONLY with a valid JSON object, in English",
        "sans_source": "Description of your photo by the model — no documentary source",
        "composants": "Visible components",
        "reperes": "Markings",
        "valeurs": "Readable values",
        "anomalies": "Apparent defects",
        "echec": "I cannot describe this image reliably.",
    },
}


def mot(cle: str, langue: str) -> str:
    return (_LANGUE.get(langue) or _LANGUE["fr"]).get(cle, _LANGUE["fr"][cle])


def construire_consigne(prompt_description: str, equipement: str, langue: str) -> str:
    """Adapte le prompt du notebook a la photo d'un technicien et a la langue de sa question."""
    consigne = prompt_description.format(
        equipement=equipement or "équipement non identifié",
        origine=", photographié sur le terrain par un technicien",
        contexte="",
    )
    if langue != "fr":
        consigne = consigne.replace(
            "Réponds UNIQUEMENT par un objet JSON valide, en français",
            mot("consigne", langue),
        )
    return consigne


def analyser(brut: str) -> dict[str, Any] | None:
    """Extrait l'objet JSON produit par le modele, ou None s'il est inexploitable."""
    trouve = _OBJET_JSON.search(brut or "")
    if not trouve:
        return None
    try:
        objet = json.loads(_VIRGULE_TRAINANTE.sub(r"\1", trouve.group(0)))
    except json.JSONDecodeError:
        return None
    return objet if isinstance(objet, dict) else None


# Le modele a pour consigne d'omettre ce qu'il ne lit pas. Il repond malgre tout « n/a » ou
# « aucune » plutot que de laisser la liste vide : ces reponses ne valent pas mieux que du vide
# et n'ont rien a faire a l'ecran.
_VIDE = frozenset(
    "n/a na none null aucun aucune aucuns aucunes neant néant - -- rien nil non applicable "
    "not applicable inconnu unknown".split()
)


def _est_vide(valeur: str) -> bool:
    return valeur.strip().strip(".·;,").lower() in _VIDE


def _liste(valeur: Any) -> list[str]:
    if isinstance(valeur, list):
        brut = [str(v).strip() for v in valeur]
    elif isinstance(valeur, str) and valeur.strip():
        brut = [valeur.strip()]
    else:
        return []
    return [v for v in brut if v and not _est_vide(v)]


def rendre(objet: dict[str, Any] | None, langue: str) -> str:
    """Met la description sous une forme lisible par un technicien.

    Les sections vides sont omises plutot qu'affichees vides : le modele a pour consigne de taire
    ce qu'il ne lit pas, et montrer « Valeurs lisibles : aucune » n'apprend rien.
    """
    if not objet:
        return mot("echec", langue)

    lignes: list[str] = []

    titre = str(objet.get("titre") or "").strip()
    description = str(objet.get("description") or "").strip()
    if titre and not _est_vide(titre):
        lignes.append(titre)
    if description and not _est_vide(description):
        lignes.append(description)

    for cle in ("composants", "reperes", "valeurs", "anomalies"):
        elements = _liste(objet.get(cle))
        if not elements:
            continue
        lignes.append(f"\n{mot(cle, langue)} : " + " · ".join(elements))

    texte = str(objet.get("texte_lisible") or "").strip()
    if texte and not _est_vide(texte):
        lignes.append(f"\n« {texte} »")

    return "\n".join(lignes).strip() or mot("echec", langue)
