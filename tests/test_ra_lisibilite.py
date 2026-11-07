"""Tests de la lisibilite des reponses : nettoyage, choix du passage, langue, bruit, intention.

Ces traitements ne changent jamais le sens d'un document — ils choisissent quoi montrer et dans
quel ordre. Une regression ici ne casse rien visiblement : elle rend seulement les reponses
inutilisables sur le terrain, ce qui est pire parce que personne ne s'en apercoit tout de suite.
"""

from __future__ import annotations

import pytest

from rda.ra.intention import cible_a_localiser
from rda.ra.lisibilite import extraire_pertinent, langue_probable, nettoyer, part_lisible

# --------------------------------------------------------------------- nettoyage


def test_l_habillage_de_page_est_retire():
    brut = (
        "www.weg.net\n"
        "6 Manuel des Moteurs Électriques\n"
        "SIAÇNARF\n"
        "2. RECOMMANDATIONS INITIALES\n"
        "Les moteurs doivent être installés par un personnel qualifié."
    )
    propre = nettoyer(brut)
    assert "www.weg.net" not in propre
    assert "SIAÇNARF" not in propre
    assert "Manuel des Moteurs" not in propre
    assert "RECOMMANDATIONS INITIALES" in propre
    assert "personnel qualifié" in propre


def test_le_contenu_utile_n_est_pas_altere():
    """Le texte restitue doit se retrouver mot pour mot dans le manuel."""
    phrase = "Le couple de serrage des boulons du flasque est de 45 N.m."
    assert phrase in nettoyer(f"www.weg.net\n{phrase}")


def test_un_texte_sans_habillage_est_rendu_tel_quel():
    phrase = "Lubrifiez les paliers avec de l'huile minérale ISO VG 68."
    assert nettoyer(phrase) == phrase


# --------------------------------------------------------------------- bruit d'extraction


@pytest.mark.parametrize(
    "ligne,bruit,pourquoi",
    [
        ("4 LLL L L L L 33 LL 3 3 5 3 5 3 3 3 33 5 33", True, "schéma de câblage aplati"),
        ("(cid:20)(cid:27)(cid:19)(cid:20)(cid:26)(cid:24)", True, "glyphes non résolus"),
        ("oC : -29 · Ω : 88.617", False, "ligne de tableau structurée"),
        ("Taille de palier : 6201 · Quantité d'huile (ml) : 15", False, "tableau"),
        ("Le moteur doit être stocké en position horizontale.", False, "phrase"),
        ("Tableau 7.5", False, "trop court pour juger"),
    ],
)
def test_detection_du_bruit_d_extraction(ligne, bruit, pourquoi):
    assert (part_lisible(ligne) < 0.5) is bruit, pourquoi


def test_un_schema_aplati_est_entierement_retire():
    assert nettoyer("4 LLL L L L L 33 LL 3 3 5 3 5 3 3 3 33 5 33 3 5 3 5") == ""


def test_un_tableau_de_valeurs_est_conserve():
    """Une valeur de resistance ou de couple se lit dans un tableau : l'ecarter serait pire."""
    tableau = "oC : -29 · Ω : 88.617\noC : -28 · Ω : 89.011"
    assert nettoyer(tableau) == tableau
    assert part_lisible(tableau) == 1.0


# --------------------------------------------------------------------- choix du passage


def test_le_passage_retenu_repond_a_la_question():
    texte = (
        "1. INTRODUCTION. Ce manuel décrit les moteurs de la gamme W22. "
        "2. TRANSPORT. Les moteurs sont expédiés en caisses de bois. "
        "3. LUBRIFICATION. Utilisez uniquement un pistolet graisseur manuel. "
        "4. GARANTIE. La garantie court sur dix-huit mois."
    )
    extrait = extraire_pertinent(texte, "pistolet graisseur manuel", max_caracteres=110)
    assert "pistolet graisseur" in extrait


def test_un_texte_court_est_rendu_entier():
    texte = "Le couple de serrage est de 45 N.m."
    assert extraire_pertinent(texte, "couple", max_caracteres=700) == texte


def test_la_coupure_est_signalee():
    """Le technicien doit savoir qu'il manque du texte avant ou apres l'extrait.

    Les phrases sont volontairement variees : un texte qui repete les memes mots des dizaines de
    fois est justement ce que le detecteur de bruit ecarte, et le test mesurerait autre chose.
    """
    debuts = [
        "Le transport s'effectue en caisses de bois.",
        "Vérifiez l'état des emballages à la réception.",
        "Stockez les moteurs à l'abri de l'humidité.",
        "L'alignement précède toute mise en service.",
        "La ventilation doit rester dégagée en permanence.",
        "Les protections thermiques sont raccordées séparément.",
        "Le sens de rotation se vérifie à vide.",
        "Les résistances de réchauffage restent hors tension.",
    ]
    texte = " ".join(debuts) + " La valeur du couple est de 45 N.m."
    extrait = extraire_pertinent(texte, "valeur du couple", max_caracteres=90)
    assert "45 N.m" in extrait
    assert extrait.startswith("…"), "la troncature en amont doit être signalée"


def test_sans_question_le_debut_est_rendu():
    texte = "www.weg.net\n" + "Phrase utile. " * 100
    extrait = extraire_pertinent(texte, "", max_caracteres=80)
    assert "www.weg.net" not in extrait


# --------------------------------------------------------------------- langue


def test_la_langue_du_francais_est_reconnue():
    assert langue_probable(
        "Le moteur doit être installé par un personnel qualifié selon les procédures."
    ) == "fr"


def test_la_langue_de_l_anglais_est_reconnue():
    assert langue_probable(
        "The motor must be installed by qualified personnel according to the procedures."
    ) == "en"


def test_une_question_francaise_courte_est_reconnue():
    assert langue_probable("Quelles sont les limites de vibration selon la norme ?") == "fr"


def test_un_texte_sans_indice_ne_tranche_pas():
    """Mieux vaut ne rien dire que se tromper : l'appelant retombe sur la langue du deploiement."""
    assert langue_probable("6201 6309 45 N.m") is None
    assert langue_probable("") is None


def test_les_accents_suffisent_a_trancher():
    assert langue_probable("Résistance d'isolation mesurée à quarante degrés.") == "fr"


# --------------------------------------------------------------------- intention


@pytest.mark.parametrize(
    "question,cible",
    [
        ("Où est le rotor ?", "rotor"),
        ("où se trouve la boîte à bornes sur la photo", "boîte à bornes"),
        ("Montre-moi le ventilateur", "ventilateur"),
        ("montre moi l'accouplement", "accouplement"),
        ("Localise le roulement côté A", "roulement côté A"),
        ("Entoure le carter", "carter"),
    ],
)
def test_une_demande_de_reperage_est_reconnue(question, cible):
    assert cible_a_localiser(question) == cible


@pytest.mark.parametrize(
    "question",
    [
        "Quel est le couple de serrage des boulons ?",
        "Quelle est la température recommandée ?",
        # « Ou » interrogatif sans objet materiel : c'est une question documentaire.
        "Où puis-je trouver le support technique en Europe ?",
        "Montre",
        "",
    ],
)
def test_une_question_documentaire_n_est_pas_un_reperage(question):
    assert cible_a_localiser(question) is None


def test_une_cible_trop_longue_est_refusee():
    """Une phrase entiere n'est pas un composant : c'est une phrase mal decoupee."""
    assert cible_a_localiser("Montre-moi " + "le composant très particulier " * 5) is None


# --------------------------------------------------------------------- langue de la reponse


def test_les_messages_du_systeme_suivent_la_langue_demandee():
    from rda.ra.messages import message

    assert "not covered" in message("abstention", "en")
    assert "pas couverte" in message("abstention", "fr")


def test_une_langue_inconnue_retombe_sur_celle_du_deploiement():
    from rda.ra.messages import message

    assert message("abstention", "de") == message("abstention", "fr")
    assert message("abstention", None) == message("abstention", "fr")


def test_toutes_les_cles_existent_dans_les_deux_langues():
    """Une cle manquante donnerait un message vide, donc une reponse sans texte."""
    from rda.ra.messages import _MESSAGES

    assert set(_MESSAGES["fr"]) == set(_MESSAGES["en"])
    assert all(v.strip() for table in _MESSAGES.values() for v in table.values())


def test_l_extrait_dans_une_autre_langue_est_signale():
    """Servir de l'anglais a un francophone est acceptable ; le faire sans le dire ne l'est pas."""
    from rda.ra.messages import mention_langue_source

    avis = mention_langue_source("fr", "en")
    assert avis and "anglais" in avis
    avis_en = mention_langue_source("en", "fr")
    assert avis_en and "French" in avis_en


def test_aucune_mention_quand_les_langues_coincident():
    from rda.ra.messages import mention_langue_source

    assert mention_langue_source("fr", "fr") is None
    assert mention_langue_source("en", "en") is None
    # Langue de source inconnue : on ne dit rien plutot que d'inventer.
    assert mention_langue_source("fr", None) is None


# --------------------------------------------------------------------- description


@pytest.mark.parametrize(
    "question",
    [
        "Qu'est-ce que c'est ?",
        "qu est ce que c est ?",
        "C'est quoi ?",
        "De quoi s'agit-il ?",
        "Décris cette image",
        "Que vois-tu ?",
        "What is this?",
        "Describe this photo",
        "ça ?",
    ],
)
def test_une_question_vague_appelle_une_description(question):
    from rda.ra.intention import est_demande_description

    assert est_demande_description(question)


@pytest.mark.parametrize(
    "question",
    [
        "Quel est le couple de serrage des boulons ?",
        "Quelle est la température recommandée pour l'air à l'entrée ?",
        "limites de vibration IEC 60034-14",
        # Un reperage laisse peu de mots porteurs mais n'est pas une demande de description.
        "Où est le rotor ?",
        "Montre-moi le stator",
        "",
    ],
)
def test_une_question_documentaire_n_appelle_pas_de_description(question):
    from rda.ra.intention import est_demande_description

    assert not est_demande_description(question)


def test_la_description_est_rendue_lisible():
    from rda.ra.description import analyser, rendre

    brut = (
        'Voici : {"type_visuel":"vue_eclatee","titre":"Vue en coupe d\'une broche",'
        '"description":"Le stator entoure le rotor central.",'
        '"composants":["stator","rotor"],"reperes":[],"valeurs":["HSK 63"],'
        '"anomalies":[],"texte_lisible":"Kühlsystem"}'
    )
    rendu = rendre(analyser(brut), "fr")
    assert "Vue en coupe" in rendu
    assert "Composants visibles : stator · rotor" in rendu
    assert "HSK 63" in rendu
    # Les sections vides ne sont pas affichees : « Repères : aucun » n'apprend rien.
    assert "Repères" not in rendu
    assert "Anomalies" not in rendu


def test_une_sortie_inexploitable_ne_produit_pas_de_description_inventee():
    from rda.ra.description import analyser, rendre

    assert analyser("je ne sais pas") is None
    assert "ne parviens pas" in rendre(None, "fr")
    assert "cannot describe" in rendre(None, "en")


def test_la_consigne_suit_la_langue_de_la_question():
    from rda.ra.description import construire_consigne

    gabarit = (
        "Tu analyses une image de « {equipement} »{origine}.\n{contexte}\n"
        "Réponds UNIQUEMENT par un objet JSON valide, en français, avec ces clés :"
    )
    assert "in English" in construire_consigne(gabarit, "Moteur", "en")
    assert "en français" in construire_consigne(gabarit, "Moteur", "fr")


@pytest.mark.parametrize("remplissage", ["n/a", "N/A", "aucune", "néant", "-", "none", "unknown"])
def test_les_valeurs_de_remplissage_sont_ecartees(remplissage):
    """Le modèle répond « n/a » au lieu de laisser la liste vide : ça ne vaut pas mieux que rien."""
    import json

    from rda.ra.description import analyser, rendre

    brut = json.dumps(
        {
            "titre": "Vue en coupe",
            "description": "Le stator entoure le rotor.",
            "composants": ["stator", remplissage],
            "reperes": [remplissage],
            "valeurs": [remplissage],
            "anomalies": [remplissage],
            "texte_lisible": remplissage,
        },
        ensure_ascii=False,
    )
    rendu = rendre(analyser(brut), "fr")
    assert remplissage not in rendu
    assert "stator" in rendu
    assert "Repères" not in rendu
    assert "Anomalies" not in rendu
