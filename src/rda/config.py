from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Parametres(BaseSettings):
    """Parametres applicatifs lus depuis l'environnement."""

    model_config = SettingsConfigDict(env_prefix="RDA_", env_file=".env", extra="ignore")

    env: str = "developpement"
    secret_jwt: str = Field(default="dev-insecure")
    duree_session_minutes: int = 480
    origines_cors: str = "http://localhost:8080,http://localhost:8081"

    db_corpus_url: str = "postgresql+asyncpg://rda_corpus_app:rda_corpus_app@localhost/rda_corpus"
    db_corpus_ingestion_url: str = (
        "postgresql+asyncpg://rda_corpus_ingestion:rda_corpus_ingestion@localhost/rda_corpus"
    )
    db_identite_url: str = (
        "postgresql+asyncpg://rda_identite_app:rda_identite_app@localhost/rda_identite"
    )
    db_intelligence_url: str = (
        "postgresql+asyncpg://rda_intelligence_app:rda_intelligence_app@localhost/rda_intelligence"
    )

    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"
    minio_bucket: str = "kalati"
    minio_secure: bool = False

    inference_url: str = "http://localhost:8080"
    artefacts_dir: Path = Path("artefacts")
    stt_modele: str = "small"
    stt_modeles_dir: Path = Path("/app/modeles/stt")

    seuil_generatif: float = 0.80
    message_abstention: str = (
        "Cette information n'est pas couverte de façon certaine par les documents auxquels vous avez accès."
    )

    @computed_field
    @property
    def liste_origines_cors(self) -> list[str]:
        return [origine.strip() for origine in self.origines_cors.split(",") if origine.strip()]


@lru_cache
def obtenir_parametres() -> Parametres:
    """Retourne les parametres mis en cache."""

    return Parametres()
