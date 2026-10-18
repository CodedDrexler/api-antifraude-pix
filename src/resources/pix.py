from typing import Annotated

from fastapi import Body, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from src.controllers.pix_controller import PixController
from src.database import get_session
from src.dtos.pix_dto import PixResponseDTO
from src.schemas.pix import PixTransactionCreate
from src.schemas.pix_examples import PIX_REQUEST_EXAMPLES


def get_pix_controller(request: Request, session: Session = Depends(get_session)):
    return PixController(
        session,
        request.app.state.policy,
        request.app.state.entity_service,
        request.app.state.temporal_service,
    )


class PixResource:
    def on_post(
        self,
        transaction: Annotated[PixTransactionCreate, Body(openapi_examples=PIX_REQUEST_EXAMPLES)],
        controller: PixController = Depends(get_pix_controller),
        include_details: Annotated[bool, Query(description="Incluir quais regras foram aplicadas.")] = False,
    ) -> PixResponseDTO:
        result = controller.analyze(transaction)
        return result.to_response(include_details=include_details)

    def on_get_by_id(
        self,
        transaction_id: Annotated[str, Path(examples=["pix-000123"])],
        controller: PixController = Depends(get_pix_controller),
        include_details: Annotated[
            bool, Query(description="Incluir os nomes das regras aplicadas na decisão salva.")
        ] = False,
    ) -> PixResponseDTO:
        result = controller.get_analysis(transaction_id)
        return result.to_response(include_details=include_details)
