from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from rda.infra.bases import BaseCorpus, BaseIdentite, BaseIntelligence
from rda.paquetages.corpus import modeles as _modeles_corpus
from rda.paquetages.identite import modeles as _modeles_identite
from rda.paquetages.reponse import modeles as _modeles_reponse

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

base = os.getenv("RDA_ALEMBIC_BASE", "identite")
metadonnees = {
    "identite": BaseIdentite.metadata,
    "corpus": BaseCorpus.metadata,
    "intelligence": BaseIntelligence.metadata,
}[base]
url = {
    "identite": os.getenv("RDA_DB_IDENTITE_URL"),
    "corpus": os.getenv("RDA_DB_CORPUS_URL"),
    "intelligence": os.getenv("RDA_DB_INTELLIGENCE_URL"),
}[base]

if url:
    config.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))

target_metadata = metadonnees


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

