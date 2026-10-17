from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from conftest import new_transaction


def post(api, payload):
    status, body, _ = api("POST", "/pix/transaction", payload)
    assert status == 200, body
    assert set(body) == {"key", "status", "metadata"}
    UUID(body["key"])
    return body


def test_contract_and_saved_decision(api, payload):
    decision = post(api, payload)
    assert decision["status"] == "approved"
    assert decision["metadata"]["reasons"] == ["no_rule_triggered"]
    status, saved, headers = api("GET", "/pix/transaction/" + payload["id"])
    assert status == 200
    assert saved == decision
    UUID(headers["X-Request-ID"])


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (1, "approved"),
        (99_999, "approved"),
        (100_000, "two_factor_required"),
        (1_999_999, "two_factor_required"),
        (2_000_000, "rejected"),
    ],
)
def test_amount_boundaries(api, payload, amount, expected):
    payload["amount"] = amount
    assert post(api, payload)["status"] == expected


@pytest.mark.parametrize(
    ("age", "expected_score"),
    [
        (timedelta(days=7), 0),
        (timedelta(days=7) - timedelta(seconds=1), 15),
    ],
)
def test_account_age_boundary(api, payload, age, expected_score):
    at = datetime.fromisoformat(payload["transaction_date"])
    payload["source_account"]["opening_date"] = (at - age).isoformat()
    decision = post(api, payload)
    assert decision["status"] == "approved"
    assert decision["metadata"]["risk_score"] == expected_score


def test_all_reasons_and_rejection_priority(api, payload):
    payload["amount"] = 2_000_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    decision = post(api, payload)
    assert decision["status"] == "rejected"
    assert decision["metadata"]["reasons"] == [
        "amount_above_rejection_limit",
        "amount_requires_two_factor",
        "new_source_account",
    ]


def test_sixth_attempt_is_rejected_and_rejections_are_saved(api, payload):
    for _ in range(5):
        assert post(api, new_transaction(payload))["status"] == "approved"
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


def seed_profile(api, payload, count, amount=1000):
    at = datetime.fromisoformat(payload["transaction_date"])
    for index in range(count):
        seed = new_transaction(
            payload, amount=amount, transaction_date=(at - timedelta(hours=index + 1)).isoformat()
        )
        assert post(api, seed)["status"] == "approved"


def test_profile_requires_five_approved_samples(api, payload):
    seed_profile(api, payload, 4, amount=10_000)
    candidate = new_transaction(payload, amount=50_000)
    assert post(api, candidate)["status"] == "approved"
    candidate = new_transaction(payload, amount=90_000)
    result = post(api, candidate)
    assert result["status"] == "approved"
    assert result["metadata"]["risk_score"] == 25
    assert "amount_above_customer_profile" in result["metadata"]["reasons"]


def test_unfamiliar_device_requires_history_and_value(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["source"]["device_id"] = "device-new"
    payload["amount"] = 50_000
    decision = post(api, payload)
    assert decision["status"] == "approved"
    assert decision["metadata"]["risk_score"] == 20
    assert "unfamiliar_device" in decision["metadata"]["reasons"]


def test_new_device_without_history_does_not_block_first_pix(api, payload):
    payload["amount"] = 50_000
    assert post(api, payload)["status"] == "approved"


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
def test_business_endpoints_require_token(api, payload, token):
    assert api("POST", "/pix/transaction", payload, token=token)[0] == 403
    assert api("GET", "/pix/transaction/" + payload["id"], token=token)[0] == 403


def test_public_health_and_openapi(api):
    assert api("GET", "/health", token=None)[:2] == (200, {"status": "ok"})
    assert api("GET", "/health_check", token=None)[0] == 204
    assert api("GET", "/ready", token=None)[0] == 204
    assert "/pix/transaction" in api("GET", "/openapi.json", token=None)[1]["paths"]


def test_concurrent_retries_share_one_analysis(api, payload):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: post(api, payload), range(6)))
    assert all(result == results[0] for result in results)
    assert post(api, new_transaction(payload))["metadata"]["recent_transactions"] == 1


def test_concurrent_distinct_pix_cannot_bypass_velocity(api, payload):
    transactions = [new_transaction(payload) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda body: post(api, body), transactions))
    assert sum(result["status"] == "approved" for result in results) == 5
    assert sum(result["status"] == "rejected" for result in results) == 1


def test_same_id_different_payers_cannot_overwrite(api, payload):
    changed = deepcopy(payload)
    changed["source_account"]["owner"]["document_number"] = "12345678909"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: api("POST", "/pix/transaction", body), [payload, changed]))
    assert sorted(result[0] for result in results) == [200, 409]


def test_known_device_does_not_challenge_normal_amount(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    assert post(api, payload)["status"] == "approved"


def test_known_destination_does_not_trigger_new_destination_rule(api, payload):
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    post(api, new_transaction(payload))
    payload["amount"] = 50_000
    decision = post(api, payload)
    assert decision["status"] == "approved"
    assert decision["metadata"]["known_destination"] is True


def test_profile_excludes_old_history(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    for index in range(5):
        post(api, new_transaction(payload, transaction_date=(at - timedelta(days=31 + index)).isoformat()))
    payload["amount"] = 50_000
    decision = post(api, payload)
    assert decision["status"] == "approved"
    assert decision["metadata"]["profile_transactions"] == 0


def test_challenged_transactions_do_not_establish_trust(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    for index in range(5):
        post(
            api,
            new_transaction(
                payload, amount=100_000, transaction_date=(at - timedelta(hours=index + 1)).isoformat()
            ),
        )
    decision = post(api, payload)
    assert decision["metadata"]["profile_transactions"] == 0
    assert decision["metadata"]["known_device"] is False


def test_velocity_is_shared_by_payer_across_accounts(api, payload):
    for index in range(5):
        candidate = new_transaction(payload)
        candidate["source_account"]["account_number"] = str(index)
        post(api, candidate)
    assert post(api, payload)["status"] == "rejected"
