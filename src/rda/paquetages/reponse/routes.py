from datetime import date
import subprocess
import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile, status

from rda.infra.transcription import ServiceTranscription
from rda.paquetages.reponse.schemas import (
    QuestionEntree,
    ReponseQuestion,
    SignalementEntree,
    SourceSortie,
    SyntheseVocaleEntree,
)
from rda.paquetages.reponse.service import ServiceReponse

routeur = APIRouter(tags=["dialogue"])
service_reponse = ServiceReponse()
service_transcription = ServiceTranscription()


def obtenir_groupes_demo(x_groupes_agent: str | None = Header(default=None)) -> list[str]:
    groupes = [g.strip() for g in (x_groupes_agent or "").split(",") if g.strip()]
    return groupes or ["DEMO_SECURITE", "SECURITE"]


def obtenir_service_reponse() -> ServiceReponse:
    return service_reponse


@routeur.post("/questions", response_model=ReponseQuestion)
async def poser_question(
    entree: QuestionEntree,
    groupes: list[str] = Depends(obtenir_groupes_demo),
    service: ServiceReponse = Depends(obtenir_service_reponse),
) -> ReponseQuestion:
    return await service.repondre(
        question=entree.question,
        groupes_resolus=groupes,
        date_reference=entree.date_reference,
    )


@routeur.get("/conversations")
async def lister_conversations() -> dict:
    return {"items": [], "total": 0}


@routeur.get("/conversations/{id_conversation}")
async def lire_conversation(id_conversation: UUID) -> dict:
    return {"id_conversation": id_conversation, "messages": []}


@routeur.post("/messages/{id_message}/signalement", status_code=status.HTTP_201_CREATED)
async def signaler_message(id_message: UUID, entree: SignalementEntree) -> dict:
    return {"id_message": id_message, "statut": "OUVERT", **entree.model_dump()}


@routeur.get("/sources/{id_passage}", response_model=SourceSortie)
async def lire_source(id_passage: UUID) -> SourceSortie:
    return SourceSortie(
        id_passage=id_passage,
        id_version=id_passage,
        reference_normative="Source non chargee",
        page=1,
        url="",
    )


@routeur.post("/vocal/transcription")
async def transcrire_vocal(audio: UploadFile = File(...)) -> dict:
    contenu = await audio.read()
    if not contenu:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fichier audio vide.")
    suffixe = "." + (audio.filename or "question.m4a").rsplit(".", 1)[-1].lower()
    resultat = await service_transcription.transcrire(contenu, suffixe=suffixe)
    return {"transcription": resultat.transcription, "confiance": resultat.confiance}


@routeur.post("/vocal/synthese")
async def synthetiser_vocal(entree: SyntheseVocaleEntree) -> Response:
    with tempfile.NamedTemporaryFile(suffix=".wav") as sortie:
        subprocess.run(
            ["espeak-ng", "-v", "fr-fr", "-s", "155", "-w", sortie.name, entree.texte],
            check=True,
            timeout=20,
        )
        sortie.seek(0)
        return Response(content=sortie.read(), media_type="audio/wav")
