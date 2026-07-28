from datetime import UTC, datetime
from uuid import uuid4

from rda.paquetages.corpus.schemas import DocumentEntree, TacheIngestionSortie


class ServiceCorpus:
    """Service d'administration du corpus; les suppressions sont logiques."""

    async def creer_tache_ingestion(self, _: DocumentEntree) -> TacheIngestionSortie:
        return TacheIngestionSortie(id_tache=uuid4(), statut="EN_ATTENTE", date_creation=datetime.now(UTC))

    async def supprimer_logiquement(self, id_document) -> dict:
        return {"id_document": id_document, "supprime": True}

