import copy
import json
import os
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from src.dtos.pix_dto import PixAnalysisDTO
from src.models.pix import PixAnalysis

API_URL = os.environ.get("PIX_API_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method, path, body=None, token=None, *, include_details=False):
    if include_details and path.startswith("/pix/transaction"):
        path += "?include_details=true"
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["INTERNAL-TOKEN"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = Request(API_URL + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as exc:
        response = exc
    with response:
        content = response.read()
        return response.status, json.loads(content) if content else None, response.headers


@pytest.fixture
def api(database_engine):
    # Rule/history integration tests inspect persisted audit evidence. Verify the
    # real HTTP summary first; details no longer expose the audit snapshot.
    def detailed_request(method, path, body=None, token=None):
        status, response, headers = request(method, path, body, token, include_details=True)
        if status == 200 and path.startswith("/pix/transaction"):
            with Session(database_engine) as session:
                saved = session.scalar(select(PixAnalysis).where(PixAnalysis.analysis_key == response["key"]))
                assert saved is not None
                audit = PixAnalysisDTO.from_model(saved)
                assert response == audit.to_response(include_details=True).model_dump(exclude_unset=True)
                response = audit.model_dump()
        return status, response, headers

    return detailed_request


@pytest.fixture
def payload():
    return {
        "id": "test-" + uuid4().hex,
        "amount": 1000,
        "transaction_date": "2026-10-17T14:00:00Z",
        "source_account": {
            "branch": "0001",
            "account_number": "88213",
            "opening_date": "2020-03-02T13:00:00Z",
            "owner": {"document_number": f"{uuid4().int % 10**11:011d}"},
        },
        "destination_account": {
            "participant": "60701190",
            "branch": "3675",
            "account_number": "destination-" + uuid4().hex,
            "opening_date": "2020-10-10T12:00:00Z",
            "owner": {"document_number": "98765432100"},
        },
        "source": {
            "device_id": "device-" + uuid4().hex,
            "channel": "app",
            "ip": "198.51.100.23",
            "geolocation": {"latitude": -23.56, "longitude": -46.65},
        },
    }


def new_transaction(payload, **changes):
    result = copy.deepcopy(payload)
    result["id"] = "test-" + uuid4().hex
    result.update(changes)
    return result


def post(api, payload):
    status, body, _ = api("POST", "/pix/transaction", payload)
    assert status == 200, body
    assert set(body) == {"key", "status", "metadata"}
    UUID(body["key"])
    return body


def seed_profile(api, payload, count, amount=1000):
    at = datetime.fromisoformat(payload["transaction_date"])
    for index in reversed(range(count)):
        seed = new_transaction(
            payload, amount=amount, transaction_date=(at - timedelta(hours=index + 1)).isoformat()
        )
        assert post(api, seed)["status"] == "approved"


@pytest.fixture
def database_engine():
    url = os.environ.get("PIX_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires the isolated verification database")
    engine = create_engine(url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()
