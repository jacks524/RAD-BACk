from datetime import timedelta

from minio import Minio

from rda.config import obtenir_parametres


def obtenir_minio() -> Minio:
    p = obtenir_parametres()
    return Minio(
        p.minio_endpoint,
        access_key=p.minio_access_key,
        secret_key=p.minio_secret_key,
        secure=p.minio_secure,
    )


def url_presignee(reference_stockage: str, duree: timedelta = timedelta(minutes=10)) -> str:
    p = obtenir_parametres()
    return obtenir_minio().presigned_get_object(p.minio_bucket, reference_stockage, expires=duree)

