from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from src.errors.pix_errors import AnalysisNotFound, PixError, TransactionConflict


def error_response(status, code, title, description, translation):
    return JSONResponse(
        status_code=status,
        content={
            "title": title,
            "description": description,
            "translation": translation,
            "code": code,
        },
    )


def register_error_handlers(app: FastAPI):
    @app.exception_handler(PixError)
    async def domain_error(request: Request, exc: PixError):
        if isinstance(exc, AnalysisNotFound):
            return error_response(404, exc.code, "Not Found", exc.description, "Análise não encontrada")
        if isinstance(exc, TransactionConflict):
            return error_response(
                409, exc.code, "Conflict", exc.description, "ID reutilizado com outro conteúdo"
            )
        return error_response(400, exc.code, "Bad Request", exc.description, "Requisição inválida")

    @app.exception_handler(RequestValidationError)
    async def invalid_schema(request: Request, exc: RequestValidationError):
        # Include field locations, never submitted documents, IPs or payloads.
        fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
        return error_response(
            400, "PIX000400", "Bad Request", "Invalid fields: " + ", ".join(fields), "Payload inválido"
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return error_response(
            503,
            "PIX000503",
            "Service Unavailable",
            "Database unavailable; retry with the same transaction ID",
            "Banco indisponível; repita com o mesmo ID",
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            exc.status_code,
            f"PIX{exc.status_code:06d}",
            "HTTP Error",
            str(exc.detail),
            "Requisição não atendida",
        )
