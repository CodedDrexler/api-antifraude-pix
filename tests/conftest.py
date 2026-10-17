import copy
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

API_URL = os.environ.get("PIX_API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("INTERNAL_TOKEN", "default_token")


def request(method, path, body=None, token=TOKEN, *, include_details=False):
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
def api():
    # Evidence-focused integration tests explicitly inspect the saved audit view.
    def detailed_request(method, path, body=None, token=TOKEN):
        return request(method, path, body, token, include_details=True)

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
