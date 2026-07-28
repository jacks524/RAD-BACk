from typing import Any

import httpx

from rda.config import obtenir_parametres


class ClientInference:
    """Client HTTP du service local d'inference."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or obtenir_parametres().inference_url).rstrip("/")

    async def verifier_sante(self) -> bool:
        async with httpx.AsyncClient(timeout=3) as client:
            reponse = await client.get(f"{self.base_url}/health")
            return reponse.status_code < 500

    async def generer(self, *, systeme: str, contexte: str, question: str) -> str:
        charge: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": systeme},
                {"role": "user", "content": f"CONTEXTE:\n{contexte}\n\nQUESTION:\n{question}"},
            ],
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            reponse = await client.post(f"{self.base_url}/v1/chat/completions", json=charge)
            reponse.raise_for_status()
            donnees = reponse.json()
            return donnees["choices"][0]["message"]["content"]

