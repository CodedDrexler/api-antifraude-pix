import hmac
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from src.errors.handlers import error_response

PUBLIC_PATHS = {"/", "/health", "/health_check", "/ready", "/docs", "/openapi.json", "/redoc"}
logger = logging.getLogger("pix.requests")


def register_request_middleware(app: FastAPI):
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid4())
        started = perf_counter()
        supplied_token = request.headers.get("INTERNAL-TOKEN", "").encode()
        if request.url.path not in PUBLIC_PATHS and not hmac.compare_digest(
            supplied_token, app.state.settings.internal_token.encode()
        ):
            response = error_response(
                403, "PIX000403", "Forbidden", "Request must be internal", "Requisição precisa ser interna"
            )
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Exception text/tracebacks may contain SQL parameters, credentials or payloads.
                logger.error(
                    json.dumps(
                        {
                            "request_id": request_id,
                            "event": "unhandled_error",
                            "exception_type": type(exc).__name__,
                        }
                    )
                )
                response = error_response(
                    500,
                    "PIX000500",
                    "Internal Server Error",
                    "Unexpected internal error",
                    "Falha interna; consulte o identificador da requisição",
                )
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "route": route.path if route else "unmatched",
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response
