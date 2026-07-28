from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status

from rda.paquetages.reponse.schemas import QuestionEntree, ReponseQuestion, SignalementEntree, SourceSortie
from rda.paquetages.reponse.service import ServiceReponse

routeur = APIRouter(tags=["dialogue"])


def obtenir_groupes_demo(x_groupes_agent: str | None = Header(default=None)) -> list[str]:
    return [g.strip() for g in (x_groupes_agent or "").split(",") if g.strip()]


def obtenir_service_reponse() -> ServiceReponse:
    return ServiceReponse()


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
async def transcrire_vocal() -> dict:
    return {"transcription": "", "confiance": 0.0}


@routeur.post("/vocal/synthese")
async def synthetiser_vocal() -> Response:
    return Response(content=b"", media_type="audio/wav")

