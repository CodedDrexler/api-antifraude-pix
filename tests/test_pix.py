"""HTTP validation, idempotency and serialization of payer activity."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction, post


def test_all_reasons_and_rejection_priority(api, payload):
    payload["amount"] = 3_000_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    decision = post(api, payload)
    assert decision["status"] == "rejected"
    assert decision["metadata"]["reasons"] == [
        "accumulated_amount_above_limit",
        "first_transaction",
        "new_source_account",
    ]


def test_sixth_attempt_is_rejected_and_rejections_are_saved(api, payload):
    for index in range(5):
        assert (
            post(api, new_transaction(payload, amount=payload["amount"] + index + 1))["status"] == "approved"
        )
    rejected = post(api, payload)
    assert rejected["status"] == "rejected"
    assert "velocity_above_limit" in rejected["metadata"]["reasons"]
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == rejected
    assert post(api, new_transaction(payload))["metadata"]["recent_transactions"] == 6


def test_retries_do_not_inflate_velocity(api, payload):
    original = post(api, payload)
    for _ in range(7):
        assert post(api, payload) == original
    assert post(api, new_transaction(payload))["metadata"]["recent_transactions"] == 1


def test_changed_payload_conflicts_and_preserves_original(api, payload):
    original = post(api, payload)
    changed = deepcopy(payload)
    changed["amount"] += 1
    status, body, _ = api("POST", "/pix/transaction", changed)
    assert status == 409
    assert body["code"] == "PIX000409"
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == original
    assert post(api, new_transaction(payload))["metadata"]["recent_transactions"] == 1


def test_equivalent_timezone_and_document_format_replay(api, payload):
    digits = f"{int(payload['id'][-12:], 16) % 10**11:011d}"
    payload["source_account"]["owner"]["document_number"] = (
        f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    )
    original = post(api, payload)
    payload["source_account"]["owner"]["document_number"] = digits
    payload["transaction_date"] = "2026-10-17T11:00:00-03:00"
    assert post(api, payload) == original


@pytest.mark.parametrize(("seconds", "expected_count"), [(600, 1), (601, 0), (-1, 0)])
def test_velocity_window_and_future_history(api, payload, seconds, expected_count):
    at = datetime.fromisoformat(payload["transaction_date"])
    post(api, new_transaction(payload, transaction_date=(at - timedelta(seconds=seconds)).isoformat()))
    assert post(api, payload)["metadata"]["recent_transactions"] == expected_count


def test_accumulated_value_boundary(api, payload):
    post(api, new_transaction(payload, amount=1_500_000))
    decision = post(api, new_transaction(payload, amount=1_500_000))
    assert decision["status"] == "rejected"
    assert "accumulated_amount_above_limit" in decision["metadata"]["reasons"]


def test_new_destination_scores_only_above_minimum(api, payload):
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    payload["amount"] = 49_999
    assert post(api, new_transaction(payload))["status"] == "approved"
    # A different, previously unseen destination.
    payload["destination_account"]["account_number"] = "unseen"
    payload["amount"] = 50_000
    result = post(api, payload)
    assert result["status"] == "approved"
    assert result["metadata"]["risk_score"] == 15
    assert "new_destination_account" in result["metadata"]["reasons"]


def test_missing_geolocation_is_valid(api, payload):
    payload["source"].pop("geolocation")
    assert post(api, payload)["status"] == "approved"


def test_cnpj_is_valid(api, payload):
    payload["source_account"]["owner"]["document_number"] = f"{int(payload['id'][-12:], 16):014d}"[-14:]
    assert post(api, payload)["status"] == "approved"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("amount",), 0),
        (("amount",), -1),
        (("amount",), 1.5),
        (("amount",), 1000.0),
        (("amount",), "1000"),
        (("amount",), True),
        (("amount",), 9_223_372_036_854_775_808),
        (("transaction_date",), "2026-10-17T14:00:00"),
        (("transaction_date",), "invalid"),
        (("id",), ""),
        (("id",), "a/b"),
        (("transaction_date",), 1_792_243_200),
        (("source_account", "opening_date"), "2026-10-18T14:00:00Z"),
        (("destination_account", "opening_date"), "2026-10-18T14:00:00Z"),
        (("source_account", "owner", "document_number"), "abc"),
        (("source", "ip"), "not-an-ip"),
        (("source", "device_id"), "   "),
        (("source", "geolocation", "latitude"), 91),
        (("source", "geolocation", "longitude"), -181),
        (("source", "geolocation", "latitude"), "-23.56"),
        (("destination_account", "participant"), None),
        (("destination_account", "participant"), "123"),
    ],
)
def test_invalid_payload_is_rejected_without_consuming_id(api, payload, path, value):
    invalid = deepcopy(payload)
    target = invalid
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    status, body, _ = api("POST", "/pix/transaction", invalid)
    assert status == 400, body
    assert set(body) == {"title", "description", "translation", "code"}
    assert api("GET", "/pix/transaction/" + payload["id"])[0] == 404
    assert post(api, payload)["status"] == "approved"


def test_required_and_unknown_fields(api, payload):
    payload["unexpected"] = True
    assert api("POST", "/pix/transaction", payload)[0] == 400
    payload.pop("unexpected")
    payload["destination_account"].pop("participant")
    assert api("POST", "/pix/transaction", payload)[0] == 400


def test_missing_transaction(api):
    assert api("GET", "/pix/transaction/nonexistent-id")[0] == 404


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_business_endpoints_accept_requests_without_internal_token(api, payload, token):
    status, decision, _ = api("POST", "/pix/transaction", payload, token=token)
    assert status == 200
    assert api("GET", "/pix/transaction/" + payload["id"], token=token)[:2] == (200, decision)


def test_public_health_and_openapi(api):
    assert api("GET", "/health", token=None)[:2] == (200, {"status": "ok"})
    assert api("GET", "/health_check", token=None)[0] == 204
    assert api("GET", "/ready", token=None)[0] == 204
    schema = api("GET", "/openapi.json", token=None)[1]
    assert "/pix/transaction" in schema["paths"]
    assert "securitySchemes" not in schema.get("components", {})
    for path in schema["paths"].values():
        for operation in path.values():
            assert "security" not in operation


def test_concurrent_retries_share_one_analysis(api, payload):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: post(api, payload), range(6)))
    assert all(result == results[0] for result in results)
    assert post(api, new_transaction(payload))["metadata"]["recent_transactions"] == 1


def test_concurrent_distinct_pix_cannot_bypass_velocity(api, payload):
    transactions = [new_transaction(payload, amount=payload["amount"] + index) for index in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda body: post(api, body), transactions))
    assert sum(result["status"] == "approved" for result in results) == 5
    assert sum(result["status"] == "two_factor_required" for result in results) == 0
    assert sum(result["status"] == "rejected" for result in results) == 1


def test_same_id_different_payers_cannot_overwrite(api, payload):
    changed = deepcopy(payload)
    changed["source_account"]["owner"]["document_number"] = "12345678909"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: api("POST", "/pix/transaction", body), [payload, changed]))
    assert sorted(result[0] for result in results) == [200, 409]


def test_velocity_is_shared_by_payer_across_accounts(api, payload):
    for index in range(5):
        candidate = new_transaction(payload)
        candidate["source_account"]["account_number"] = str(index)
        post(api, candidate)
    assert post(api, payload)["status"] == "rejected"
