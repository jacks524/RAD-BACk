"""Module backend RDA consacre a cache."""

from hashlib import sha256

from redis.asyncio import Redis

from rda.config import obtenir_parametres


def obtenir_redis() -> Redis:
    return Redis.from_url(obtenir_parametres().redis_url, decode_responses=True)


def cle_cache_question(question_normalisee: str, groupes_resolus: list[str], date_reference: str) -> str:
    """Construit une cle cache cloisonnee par habilitations."""

    empreinte = sha256()
    empreinte.update(question_normalisee.encode("utf-8"))
    empreinte.update("|".join(sorted(groupes_resolus)).encode("utf-8"))
    empreinte.update(date_reference.encode("utf-8"))
    return f"rda:question:{empreinte.hexdigest()}"

