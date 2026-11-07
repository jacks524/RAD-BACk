"""Agent du module RA : perception, recherche, deliberation, action, verification.

Portage fidele de la cellule 32 du notebook. L'enchainement est celui d'un fil de dialogue unique,
et la decision de repondre ou de se taire appartient a ce module — jamais au modele.

Specification : docs/spec-module-ra.md, section 6.4.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Iterable

import numpy as np

from rda.ra import deliberation as D
from rda.ra import recherche as R
from rda.ra.clients import ClientEncodeurs, ClientVision, ServiceIndisponible
from rda.ra.config import obtenir_parametres_ra
from rda.ra.etat import EtatRA
from rda.ra.generation import construire_messages, reponse_extractive
from rda.ra.glossaire import enrichir_requete
from rda.ra.identification import identifier
from rda.ra.description import analyser, construire_consigne, mot, rendre
from rda.ra.intention import cible_a_localiser, est_demande_description
from rda.ra.lisibilite import langue_probable, part_lisible
from rda.ra.messages import mention_langue_source, message
from rda.ra.localisation import CONSIGNE, extraire_boites

journal = logging.getLogger("rda.ra")



class AgentRA:
    """Orchestre une question de bout en bout."""

    def __init__(
        self,
        etat: EtatRA,
        encodeurs: ClientEncodeurs | None = None,
        vision: ClientVision | None = None,
    ):
        self.etat = etat
        self.encodeurs = encodeurs or ClientEncodeurs()
        self.vision = vision or ClientVision()

    # ------------------------------------------------------------------ question

    async def repondre(
        self,
        question: str,
        *,
        groupes: list[str],
        equipement: str | None = None,
        photo_jpeg: bytes | None = None,
        date_reference: str | None = None,
        canaux: Iterable[str] | None = None,
        types: Iterable[str] | None = None,
        dimensions_photo: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        depart = time.monotonic()
        parametres = obtenir_parametres_ra()

        # La langue de la reponse est celle de la question, decidee une fois et appliquee
        # partout. Une question trop courte pour qu'on la devine retombe sur la langue de
        # travail du deploiement.
        langue = langue_probable(question) or parametres.langue_preferee

        def terminer(resultat: dict[str, Any]) -> dict[str, Any]:
            return {
                **resultat,
                "equipement": equipement,
                "langue": langue,
                "latence_s": round(time.monotonic() - depart, 2),
            }

        # --- 1. perception ------------------------------------------------
        if D.est_injection(question):
            return terminer(
                {
                    "mode": D.MODE_NEUTRALISATION,
                    "confiance": 0.0,
                    "citations": [],
                    "reponse": message("neutralisation", langue),
                }
            )
        if D.est_civilite(question):
            return terminer(
                {
                    "mode": D.MODE_CONVERSATION,
                    "confiance": 1.0,
                    "citations": [],
                    "reponse": message("accueil", langue),
                }
            )

        identification = None
        if photo_jpeg is not None and equipement is None:
            identification = await self.identifier_par_photo(photo_jpeg, groupes=groupes)
            if identification.get("confiant"):
                equipement = identification["equipement_id"]

        # --- 1 bis. description de la photo -------------------------------
        # « Qu'est-ce que c'est ? » n'a pas de reponse dans un manuel : la recherche ne trouve
        # rien et le systeme se tait, alors qu'une photo est sous ses yeux. On decrit.
        if photo_jpeg is not None and est_demande_description(question):
            return terminer(
                await self.decrire(
                    photo_jpeg,
                    langue=langue,
                    equipement=equipement,
                    identification=identification,
                )
            )

        # --- 1 ter. reperage sur la photo ---------------------------------
        # « Ou est le rotor ? » avec une photo n'appelle pas la meme chose qu'une question de
        # valeur : le technicien veut voir la piece sur SA machine, puis savoir ce qu'elle fait.
        # On fait les deux, et la recherche documentaire porte alors sur le composant nomme.
        boites: list[dict[str, Any]] = []
        cible = cible_a_localiser(question) if photo_jpeg is not None else None
        if cible and dimensions_photo:
            try:
                reperage = await self.localiser(
                    photo_jpeg, cible, dimensions_photo[0], dimensions_photo[1]
                )
                boites = reperage["boites"]
            except ServiceIndisponible as erreur:
                # Le reperage echoue, l'explication reste possible : on continue sans boite
                # plutot que de renvoyer le technicien sans rien.
                journal.warning("reperage impossible : %s", erreur.detail)

        # --- 2. recherche -------------------------------------------------
        candidats = await self._rechercher(
            cible or question,
            groupes=groupes,
            equipement=equipement,
            photo_jpeg=photo_jpeg,
            date_reference=date_reference,
            canaux=canaux,
            types=types,
        )
        if not candidats:
            return terminer(
                {
                    "mode": D.MODE_ABSTENTION,
                    "confiance": 0.0,
                    "citations": [],
                    "identification": identification,
                    "cible": cible,
                    "boites": boites,
                    "reponse": message("aucun_document", langue),
                }
            )

        # --- 3. deliberation ----------------------------------------------
        elements = self.etat.elements
        politique = self.etat.politique
        textes = [elements[c.position]["texte"] for c in candidats]
        scores = await self.encodeurs.reclasser(question, textes)

        # Preference de langue. Le corpus contient le meme manuel constructeur en francais et en
        # anglais : sans cela, une question francaise peut se voir citer la version anglaise. Le
        # contenu est exact, mais inexploitable par un technicien qui ne lit pas l'anglais.
        # C'est une penalite, pas un filtre : un document qui n'existe que dans l'autre langue
        # reste citable plutot que de laisser le technicien sans rien.
        langue_question = langue
        penalite = float(parametres.penalite_autre_langue)

        penalite_illisible = float(parametres.penalite_illisible)
        seuil_lisibilite = float(parametres.seuil_lisibilite)

        for candidat, score in zip(candidats, scores):
            element = elements[candidat.position]
            ecart = 0.0
            langue_source = self.etat.langue_document.get(element["cle_doc"])
            if langue_source and langue_source != langue_question:
                ecart += penalite
            if part_lisible(element["texte"]) < seuil_lisibilite:
                ecart += penalite_illisible
            candidat.score_reclassement = float(score) - ecart

        retenus, confiance = D.calibrer(candidats, int(politique["k_final"]))
        famille = elements[retenus[0].position]["famille"]
        seuil = D.seuil_abstention(famille, politique["seuils_abstention"])

        if confiance < seuil:
            proches = [elements[c.position]["titre_doc"] for c in retenus[:3]]
            # La phrase de politique.json est en francais : on ne l'utilise que pour une
            # question francaise, sans quoi le technicien anglophone lirait du francais.
            phrase = (
                politique["phrase_abstention"] if langue == "fr" else message("abstention", langue)
            )
            return terminer(
                {
                    "mode": D.MODE_ABSTENTION,
                    "confiance": round(confiance, 3),
                    "seuil": seuil,
                    "perimetre": famille,
                    "citations": [],
                    "identification": identification,
                    "cible": cible,
                    "boites": boites,
                    "reponse": f"{phrase} {message('documents_proches', langue)} : "
                    + " ; ".join(dict.fromkeys(proches))
                    + ".",
                }
            )

        # --- 4. action ----------------------------------------------------
        mode = (
            D.MODE_GENERATIF
            if confiance >= float(politique["seuil_generatif"])
            else D.MODE_EXTRACTIF
        )
        texte = ""

        if mode == D.MODE_GENERATIF:
            try:
                texte = await self._generer(question, retenus, photo_jpeg)
            except ServiceIndisponible as erreur:
                # Seul le modele de vision manque : la recherche a reussi, les sources sont la.
                # Restituer la source brute vaut mieux que refuser la question.
                journal.warning("ra-vision indisponible, repli extractif : %s", erreur.detail)
                mode = D.MODE_EXTRACTIF
            else:
                if politique["phrase_abstention"][:40] in texte:
                    return terminer(
                        {
                            "mode": D.MODE_ABSTENTION,
                            "confiance": round(confiance, 3),
                            "seuil": seuil,
                            "perimetre": famille,
                            "citations": [],
                            "identification": identification,
                            "reponse": politique["phrase_abstention"],
                        }
                    )
                # --- 5. verification d'ancrage ---------------------------
                if not D.reponse_ancree(texte, len(retenus)):
                    journal.info("reponse non etayee, repli extractif")
                    mode = D.MODE_EXTRACTIF

        if mode == D.MODE_EXTRACTIF:
            texte = reponse_extractive(retenus, elements, question)

        citations = D.construire_citations(retenus, elements, question)
        langue_citee = self.etat.langue_document.get(elements[retenus[0].position]["cle_doc"])
        return terminer(
            {
                "mode": mode,
                "mention_source": mention_langue_source(langue, langue_citee),
                "cible": cible,
                "boites": boites,
                "confiance": round(confiance, 3),
                "seuil": seuil,
                "perimetre": famille,
                "reponse": texte,
                "citations": citations,
                "identification": identification,
                "images": [c["image"] for c in citations if c["image"]][
                    : int(politique["max_images_reponse"])
                ],
            }
        )

    # ------------------------------------------------------------------ recherche

    async def _rechercher(
        self,
        question: str,
        *,
        groupes: list[str],
        equipement: str | None,
        photo_jpeg: bytes | None,
        date_reference: str | None,
        canaux: Iterable[str] | None,
        types: Iterable[str] | None,
    ) -> list[R.Candidat]:
        etat = self.etat
        politique = etat.politique
        k = int(politique["k_recuperation"])
        canaux_actifs = set(canaux) if canaux else set(R.CANAUX)

        masque = R.masque_autorise(
            etat.elements,
            groupes=groupes,
            equipement=equipement,
            types=types,
            date_reference=date_reference or date.today().isoformat(),
        )
        if not masque.any():
            return []

        question_enrichie = enrichir_requete(question, etat.glossaire)
        nombre = len(etat.elements)
        scores_dense = scores_lexical = scores_it = scores_ii = None

        if "dense" in canaux_actifs:
            vecteur = np.asarray(
                (await self.encodeurs.encoder_texte([question_enrichie], "query"))[0],
                dtype=np.float32,
            )
            scores_dense = etat.vecteurs_texte @ vecteur

        if "lexical" in canaux_actifs and etat.index_lexical is not None:
            scores_lexical = etat.index_lexical.scores(question_enrichie)

        if len(etat.positions_visuelles):
            # Canal image_texte : la question BRUTE, sans enrichissement. SigLIP2 n'a pas ete
            # entraine sur le glossaire metier ; les synonymes ajoutes ne feraient que bruiter.
            if "image_texte" in canaux_actifs and question.strip():
                vecteur = np.asarray(
                    (await self.encodeurs.encoder_visuel_texte([question]))[0], dtype=np.float32
                )
                scores_it = R.scores_visuels(
                    vecteur, etat.vecteurs_image, etat.positions_visuelles, nombre
                )
            if "image_image" in canaux_actifs and photo_jpeg is not None:
                vecteur = np.asarray(
                    (await self.encodeurs.encoder_visuel_image([photo_jpeg]))[0], dtype=np.float32
                )
                scores_ii = R.scores_visuels(
                    vecteur, etat.vecteurs_image, etat.positions_visuelles, nombre
                )

        return R.rechercher(
            elements=etat.elements,
            masque=masque,
            scores_dense=scores_dense,
            scores_lexical=scores_lexical,
            scores_image_texte=scores_it,
            scores_image_image=scores_ii,
            poids=politique["poids_canaux"],
            rrf_k=int(politique["rrf_k"]),
            k=k,
        )

    # ------------------------------------------------------------------ generation

    async def _generer(
        self, question: str, retenus: list[R.Candidat], photo_jpeg: bytes | None
    ) -> str:
        politique = self.etat.politique
        messages = construire_messages(
            question,
            retenus,
            self.etat.elements,
            prompt_systeme=politique["prompt_systeme"],
            max_images=int(politique["max_images_reponse"]),
            dossier_artefacts=self.etat.dossier,
            photo_jpeg=photo_jpeg,
        )
        return await self.vision.completer(messages, max_tokens=512)

    # ------------------------------------------------------------------ identification

    async def identifier_par_photo(
        self, photo_jpeg: bytes, *, groupes: list[str], exclure: Iterable[str] | None = None
    ) -> dict[str, Any]:
        etat = self.etat
        if not len(etat.positions_visuelles):
            return {"confiant": False, "raison": "aucun visuel indexé"}

        vecteur = np.asarray(
            (await self.encodeurs.encoder_visuel_image([photo_jpeg]))[0], dtype=np.float32
        )
        politique = etat.politique
        return identifier(
            vecteur,
            vecteurs_image=etat.vecteurs_image,
            positions_visuelles=etat.positions_visuelles,
            elements=etat.elements,
            equipements=etat.equipements,
            seuil=float(politique["seuil_identification"]),
            marge=float(politique["marge_identification"]),
            groupes=groupes,
            exclure=exclure,
        )

    # ------------------------------------------------------------------ localisation

    async def localiser(
        self, photo_jpeg: bytes, cible: str, largeur: int, hauteur: int
    ) -> dict[str, Any]:
        depart = time.monotonic()
        politique = self.etat.politique
        # La cle de politique.json est « vlm_max_pixels_reponse ». Lire « vlm_max_pixels »
        # retombait silencieusement sur la valeur par defaut, soit 60 % de pixels en trop — et
        # surtout un facteur d'echelle faux, donc des boites decalees.
        max_pixels = int(
            politique.get("vlm_max_pixels_reponse")
            or politique.get("vlm_max_pixels")
            or 1024 * 28 * 28
        )
        min_pixels = int(politique.get("vlm_min_pixels") or 256 * 28 * 28)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": ClientVision.image_en_url(photo_jpeg)},
                    },
                    {"type": "text", "text": CONSIGNE.format(cible=cible)},
                ],
            }
        ]
        from rda.ra.config import obtenir_parametres_ra

        brut = await self.vision.completer(
            messages, max_tokens=200, delai=obtenir_parametres_ra().delai_localisation
        )
        boites = extraire_boites(
            brut,
            cible=cible,
            largeur_photo=largeur,
            hauteur_photo=hauteur,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )
        return {
            "cible": cible,
            "boites": boites,
            "brut": brut,
            "latence_s": round(time.monotonic() - depart, 2),
        }

    # ------------------------------------------------------------------ description

    async def decrire(
        self,
        photo_jpeg: bytes,
        *,
        langue: str,
        equipement: str | None = None,
        identification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Decrit la photo du technicien, sans rien citer.

        Le resultat n'est pas une reponse documentaire et ne doit jamais etre presente comme
        telle : aucune source ne l'etaye. D'ou un mode distinct et une mention explicite.
        """
        politique = self.etat.politique
        nom = (
            (identification or {}).get("equipement_nom")
            or (self.etat.equipements.get(equipement or "") or {}).get("nom")
            or equipement
            or ""
        )
        consigne = construire_consigne(politique["prompt_description"], nom, langue)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": ClientVision.image_en_url(photo_jpeg)},
                    },
                    {"type": "text", "text": consigne},
                ],
            }
        ]

        try:
            brut = await self.vision.completer(messages, max_tokens=600)
        except ServiceIndisponible as erreur:
            journal.warning("description impossible : %s", erreur.detail)
            return {
                "mode": D.MODE_ABSTENTION,
                "confiance": 0.0,
                "citations": [],
                "identification": identification,
                "reponse": message("aucun_document", langue),
            }

        return {
            "mode": D.MODE_DESCRIPTION,
            "confiance": 0.0,
            "seuil": None,
            "citations": [],
            "identification": identification,
            "mention_source": mot("sans_source", langue),
            "reponse": rendre(analyser(brut), langue),
        }
