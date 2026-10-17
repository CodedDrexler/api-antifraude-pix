import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.constants import Policy, Settings
from src.database import build_database
from src.dtos.pix_dto import PixAnalysisDTO
from src.errors.handlers import register_error_handlers
from src.middlewares.request_context import register_request_middleware
from src.resources.health_check import HealthCheckResource
from src.resources.pix import PixResource


def create_app(settings: Settings | None = None, policy: Policy | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine, session_factory = build_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(application):
        yield
        engine.dispose()

    application = FastAPI(title="Pix Antifraude", version="2.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.policy = policy or Policy()
    application.state.session_factory = session_factory
    health = HealthCheckResource()
    pix = PixResource()
    application.add_api_route("/health", health.on_get_health, methods=["GET"], tags=["health"])
    application.add_api_route("/health_check", health.on_get_health_check, methods=["GET"], tags=["health"])
    application.add_api_route("/ready", health.on_get_ready, methods=["GET"], tags=["health"])
    application.add_api_route(
        "/pix/transaction", pix.on_post, methods=["POST"], response_model=PixAnalysisDTO, tags=["pix"]
    )
    application.add_api_route(
        "/pix/transaction/{transaction_id}",
        pix.on_get_by_id,
        methods=["GET"],
        response_model=PixAnalysisDTO,
        tags=["pix"],
    )
    register_error_handlers(application)
    register_request_middleware(application)
    return application


logging.basicConfig(level=logging.INFO, format="%(message)s")
app = create_app()
