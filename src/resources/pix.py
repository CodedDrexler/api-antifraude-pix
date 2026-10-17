from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.controllers.pix_controller import PixController
from src.database import get_session
from src.dtos.pix_dto import PixAnalysisDTO
from src.schemas.pix import PixTransactionCreate


def get_pix_controller(request: Request, session: Session = Depends(get_session)):
    return PixController(session, request.app.state.policy, request.app.state.graph_service)


class PixResource:
    def on_post(
        self, transaction: PixTransactionCreate, controller: PixController = Depends(get_pix_controller)
    ) -> PixAnalysisDTO:
        return controller.analyze(transaction)

    def on_get_by_id(
        self, transaction_id: str, controller: PixController = Depends(get_pix_controller)
    ) -> PixAnalysisDTO:
        return controller.get_analysis(transaction_id)
