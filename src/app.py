import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.security import APIKeyHeader

from src.constants import Policy, Settings
from src.database import build_database
from src.dtos.pix_dto import PixAnalysisDTO
from src.errors.handlers import register_error_handlers
from src.gnn.service import DEFAULT_MODEL, GraphRiskService
from src.middlewares.request_context import register_request_middleware
from src.middlewares.request_limits import RequestLimitsMiddleware
from src.resources.health_check import HealthCheckResource
from src.resources.pix import PixResource


def create_app(settings: Settings | None = None, policy: Policy | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine, session_factory = build_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(application):
        yield
        engine.dispose()

    application = FastAPI(
        title="Pix Antifraude",
        version="2.3.0",
        lifespan=lifespan,
        openapi_tags=[{"name": "pix"}, {"name": "health"}],
        swagger_ui_parameters={"defaultModelsExpandDepth": 0},
        description=(
            "Analisa um Pix e responde: **approved** (aprovar), **two_factor_required** "
            "(solicitar autenticação adicional) ou **rejected** (bloquear).\n\n"
            "1. Clique em **Authorize** e informe o token interno (local: `default_token`).\n"
            "2. Envie um Pix com um ID novo. Valores são inteiros em centavos. O primeiro Pix exige 2FA.\n"
            "3. Consulte o mesmo ID para recuperar a decisão salva. Ative `include_details` para ver a evidência.\n\n"
            "O score vai de 0 a 100 e não representa probabilidade de fraude. "
            "O GNN é experimental, treinado com dados sintéticos e, no padrão shadow, apenas observa. "
            "A metadata também mostra a desconfiança acumulada da conta e um indicativo de aviso ao banco, sem envio externo. "
            "O serviço não executa 2FA, liquidação ou gestão dos limites bancários do Pix."
        ),
    )
    application.state.settings = settings
    policy_path = os.environ.get("RISK_POLICY_PATH")
    application.state.policy = policy or (Policy.from_file(policy_path) if policy_path else Policy())
    application.state.session_factory = session_factory
    application.state.graph_service = GraphRiskService(
        mode=os.environ.get("GNN_MODE", "shadow"),
        model_path=os.environ.get("GNN_MODEL_PATH", str(DEFAULT_MODEL)),
    )
    health = HealthCheckResource()
    pix = PixResource()
    internal_token = APIKeyHeader(
        name="INTERNAL-TOKEN",
        scheme_name="InternalToken",
        description="Informe o INTERNAL_TOKEN configurado na API (padrão local: default_token).",
        auto_error=False,
    )
    application.add_api_route(
        "/health",
        health.on_get_health,
        methods=["GET"],
        tags=["health"],
        summary="Consultar o serviço",
    )
    application.add_api_route(
        "/health_check",
        health.on_get_health_check,
        methods=["GET"],
        tags=["health"],
        summary="Verificar o processo",
    )
    application.add_api_route(
        "/ready",
        health.on_get_ready,
        methods=["GET"],
        tags=["health"],
        summary="Verificar o banco de dados",
    )
    application.add_api_route(
        "/pix/transaction",
        pix.on_post,
        methods=["POST"],
        response_model=PixAnalysisDTO,
        tags=["pix"],
        dependencies=[Depends(internal_token)],
        summary="Analisar um Pix",
        description="Grava a análise e os motivos. Mesmo ID e conteúdo retornam a decisão original; conteúdo diferente gera 409.",
    )
    application.add_api_route(
        "/pix/transaction/{transaction_id}",
        pix.on_get_by_id,
        methods=["GET"],
        response_model=PixAnalysisDTO,
        tags=["pix"],
        dependencies=[Depends(internal_token)],
        summary="Consultar uma análise",
        description="Recupera a decisão original, sem recalcular o risco ou executar o GNN novamente.",
    )
    register_error_handlers(application)
    # Request context/authentication wraps this middleware: unauthorized callers
    # are rejected before we receive or buffer their bodies.
    application.add_middleware(RequestLimitsMiddleware)
    register_request_middleware(application)
    return application


logging.basicConfig(level=logging.INFO, format="%(message)s")
app = create_app()
