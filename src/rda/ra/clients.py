"""Clients HTTP vers les deux services d'inference du module RA.

Aucun appel ne peut faire tomber une route : un service indisponible ou trop lent leve une
ErreurRDA explicite, que l'agent traduit en abstention ou en repli extractif. Une reponse de
maintenance vaut mieux absente que fausse, mais l'API ne doit jamais renvoyer une trace.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from rda.commun.erreurs import ErreurRDA
from rda.ra.config import obtenir_parametres_ra


class ServiceIndisponible(ErreurRDA):
    """Un service d'inference ne repond pas, ou pas dans le delai imparti."""

    def __init__(self, service: str, cause: str):
        super().__init__(
            code="RA_SERVICE_INDISPONIBLE",
            message=f"Le service {service} est indisponible.",
            detail={"service": service, "cause": cause},
            statut=503,
        )


class ClientEncodeurs:
    """Encodeur texte (e5), encodeur visuel (SigLIP2) et reclasseur.

    Les trois espaces vectoriels sont distincts et ne se melangent jamais : une requete encodee
    par e5 n'a aucun sens dans l'espace SigLIP2, et reciproquement.
    """

    def __init__(self, base_url: str | None = None, delai: float | None = None):
        parametres = obtenir_parametres_ra()
        self.base_url = (base_url or parametres.encodeurs_url).rstrip("/")
        self.delai = delai if delai is not None else parametres.delai_encodeurs

    async def _appeler(self, chemin: str, charge: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.delai) as client:
                reponse = await client.post(f"{self.base_url}{chemin}", json=charge)
                reponse.raise_for_status()
                return reponse.json()
        except httpx.TimeoutException as erreur:
            raise ServiceIndisponible("ra-encodeurs", f"delai de {self.delai}s depasse") from erreur
        except httpx.HTTPError as erreur:
            raise ServiceIndisponible("ra-encodeurs", str(erreur)) from erreur

    async def encoder_texte(self, textes: list[str], prefixe: str) -> list[list[float]]:
        """Encode avec e5. Le prefixe est « passage » pour indexer, « query » pour interroger."""
        if prefixe not in ("passage", "query"):
            raise ValueError(f"prefixe e5 invalide : {prefixe!r}")
        charge = await self._appeler("/encoder/texte", {"textes": textes, "prefixe": prefixe})
        return charge["vecteurs"]

    async def encoder_visuel_texte(self, textes: list[str]) -> list[list[float]]:
        """Projette un texte dans l'espace SigLIP2, pour le canal image_texte."""
        charge = await self._appeler("/encoder/visuel-texte", {"textes": textes})
        return charge["vecteurs"]

    async def encoder_visuel_image(self, images: list[bytes]) -> list[list[float]]:
        """Encode des images dans l'espace SigLIP2, pour le canal image_image et l'identification."""
        charge = await self._appeler(
            "/encoder/visuel-image",
            {"images_base64": [base64.b64encode(i).decode("ascii") for i in images]},
        )
        return charge["vecteurs"]

    async def reclasser(self, question: str, textes: list[str]) -> list[float]:
        """Note les paires (question, texte). Scores bruts : la calibration reste cote agent."""
        charge = await self._appeler("/reclasser", {"question": question, "textes": textes})
        return charge["scores"]

    async def sante(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=obtenir_parametres_ra().delai_sante) as client:
                reponse = await client.get(f"{self.base_url}/sante")
                reponse.raise_for_status()
                return reponse.json()
        except httpx.HTTPError as erreur:
            return {"statut": "INDISPONIBLE", "cause": str(erreur)}


class ClientVision:
    """Modele vision-langage servi par llama.cpp, au format de dialogue OpenAI.

    Les images voyagent en data URL base64 dans le message : le serveur ne lit aucun fichier du
    disque, ce qui evite qu'une reference d'image puisse servir a lire autre chose.
    """

    def __init__(self, base_url: str | None = None, delai: float | None = None):
        parametres = obtenir_parametres_ra()
        self.base_url = (base_url or parametres.vision_url).rstrip("/")
        self.delai = delai if delai is not None else parametres.delai_vision

    @staticmethod
    def image_en_url(donnees: bytes, type_mime: str = "image/jpeg") -> str:
        return f"data:{type_mime};base64,{base64.b64encode(donnees).decode('ascii')}"

    async def completer(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        delai: float | None = None,
    ) -> str:
        """Un appel au modele. Echantillonnage desactive par defaut, comme a l'evaluation."""
        charge = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "repeat_penalty": 1.05,
        }
        attente = delai if delai is not None else self.delai
        try:
            async with httpx.AsyncClient(timeout=attente) as client:
                reponse = await client.post(f"{self.base_url}/v1/chat/completions", json=charge)
                reponse.raise_for_status()
                donnees = reponse.json()
        except httpx.TimeoutException as erreur:
            raise ServiceIndisponible("ra-vision", f"delai de {attente}s depasse") from erreur
        except httpx.HTTPError as erreur:
            raise ServiceIndisponible("ra-vision", str(erreur)) from erreur

        try:
            return donnees["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as erreur:
            raise ServiceIndisponible("ra-vision", f"reponse inattendue : {donnees}") from erreur

    async def sante(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=obtenir_parametres_ra().delai_sante) as client:
                reponse = await client.get(f"{self.base_url}/health")
                return {"statut": "OK" if reponse.status_code < 500 else "DEGRADE"}
        except httpx.HTTPError as erreur:
            return {"statut": "INDISPONIBLE", "cause": str(erreur)}
