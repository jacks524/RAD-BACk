from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import UserDefinedType

from rda.config import obtenir_parametres

convention_nommage = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseIdentite(DeclarativeBase):
    metadata = MetaData(naming_convention=convention_nommage)


class BaseCorpus(DeclarativeBase):
    metadata = MetaData(naming_convention=convention_nommage)


class BaseIntelligence(DeclarativeBase):
    metadata = MetaData(naming_convention=convention_nommage)


class VecteurPg(UserDefinedType):
    """Type pgvector declare sans dependance Python externe."""

    cache_ok = True

    def __init__(self, dimensions: int = 768):
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"


ClePrimaireUUID = Annotated[str, mapped_column(primary_key=True)]

parametres = obtenir_parametres()

moteur_corpus: AsyncEngine = create_async_engine(parametres.db_corpus_url, pool_pre_ping=True)
moteur_corpus_ingestion: AsyncEngine = create_async_engine(
    parametres.db_corpus_ingestion_url, pool_pre_ping=True
)
moteur_identite: AsyncEngine = create_async_engine(parametres.db_identite_url, pool_pre_ping=True)
moteur_intelligence: AsyncEngine = create_async_engine(
    parametres.db_intelligence_url, pool_pre_ping=True
)

SessionCorpus = async_sessionmaker(moteur_corpus, expire_on_commit=False)
SessionCorpusIngestion = async_sessionmaker(moteur_corpus_ingestion, expire_on_commit=False)
SessionIdentite = async_sessionmaker(moteur_identite, expire_on_commit=False)
SessionIntelligence = async_sessionmaker(moteur_intelligence, expire_on_commit=False)


async def session_identite() -> AsyncIterator[AsyncSession]:
    async with SessionIdentite() as session:
        yield session


async def session_intelligence() -> AsyncIterator[AsyncSession]:
    async with SessionIntelligence() as session:
        yield session


async def session_corpus_dialogue() -> AsyncIterator[AsyncSession]:
    async with SessionCorpus() as session:
        yield session


@asynccontextmanager
async def transaction_corpus_habilitee(
    groupes_resolus: list[str],
) -> AsyncIterator[AsyncSession]:
    """Ouvre une transaction de lecture corpus avec le contexte RLS obligatoire."""

    async with SessionCorpus() as session:
        async with session.begin():
            groupes = ",".join(sorted(groupes_resolus))
            await session.execute(text("SET LOCAL app.groupes_agent = :groupes"), {"groupes": groupes})
            yield session


@asynccontextmanager
async def transaction_corpus_ingestion() -> AsyncIterator[AsyncSession]:
    async with SessionCorpusIngestion() as session:
        async with session.begin():
            yield session

