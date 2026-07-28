from fastapi import Request
from fastapi.responses import JSONResponse


class ErreurRDA(Exception):
    """Erreur metier exposee sous forme JSON normalisee."""

    def __init__(self, code: str, message: str, detail: dict | None = None, statut: int = 400):
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.statut = statut


async def gerer_erreur_rda(_: Request, exc: ErreurRDA) -> JSONResponse:
    return JSONResponse(
        status_code=exc.statut,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )

