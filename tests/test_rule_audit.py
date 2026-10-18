"""Activation boundaries and exclusions for every rule; decision priority lives in test_scoring_policy."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate

POLICY = Policy.from_file(str(Path(__file__).resolve().parents[1] / "config/risk-policy.json"))
BASE_HISTORY = History(0, 0, 3, True, True, 3, 60_000, registered_count=4, profile_basis="approved")
NO_REFERENCE = {
    "approved_count": 0,
    "known_device": False,
    "known_destination": False,
    "profile_count": 0,
    "profile_amount": 0,
    "profile_basis": "unavailable",
}


def case(code, active, scenario, *, history=None, changes=None):
    return pytest.param(code, active, history or {}, changes or {}, id=f"{code}-{scenario}")


RULE_CASES = [
    case("velocity_above_limit", False, "below-five-prior-attempts", history={"recent_count": 4}),
    case("velocity_above_limit", True, "at-five-prior-attempts", history={"recent_count": 5}),
    case("velocity_above_limit", True, "above-five-prior-attempts", history={"recent_count": 6}),
    case(
        "accumulated_amount_above_limit",
        False,
        "one-cent-below-total-limit",
        history={"recent_amount": 2_949_999},
    ),
    case("accumulated_amount_above_limit", True, "at-total-limit", history={"recent_amount": 2_950_000}),
    case(
        "accumulated_amount_above_limit",
        True,
        "one-cent-above-total-limit",
        history={"recent_amount": 2_950_001},
    ),
    case(
        "first_transaction", True, "no-registered-attempts", history={**NO_REFERENCE, "registered_count": 0}
    ),
    case(
        "first_transaction", False, "previous-attempt-exists", history={**NO_REFERENCE, "registered_count": 1}
    ),
    case(
        "insufficient_amount_history",
        True,
        "attempt-without-eligible-reference",
        history={**NO_REFERENCE, "registered_count": 1},
    ),
    case(
        "insufficient_amount_history",
        False,
        "first-pix-has-own-rule",
        history={**NO_REFERENCE, "registered_count": 0},
    ),
    case("insufficient_amount_history", False, "eligible-reference-exists"),
    case("new_source_account", True, "one-second-before-seven-days", changes={"source_age_seconds": 604_799}),
    case("new_source_account", False, "exactly-seven-days", changes={"source_age_seconds": 604_800}),
    case("new_source_account", False, "one-second-after-seven-days", changes={"source_age_seconds": 604_801}),
    case(
        "new_destination_account",
        True,
        "unknown-young-destination",
        history={"known_destination": False},
        changes={"destination_age_seconds": 604_799},
    ),
    case(
        "new_destination_account",
        False,
        "destination-exactly-seven-days",
        history={"known_destination": False},
        changes={"destination_age_seconds": 604_800},
    ),
    case(
        "new_destination_account",
        False,
        "below-minimum-value",
        history={"known_destination": False},
        changes={"destination_age_seconds": 1, "amount": 49_999},
    ),
    case(
        "new_destination_account", False, "destination-already-known", changes={"destination_age_seconds": 1}
    ),
    case(
        "unfamiliar_destination", True, "unknown-with-three-approvals", history={"known_destination": False}
    ),
    case(
        "unfamiliar_destination",
        False,
        "fewer-than-three-approvals",
        history={"known_destination": False, "approved_count": 2},
    ),
    case(
        "unfamiliar_destination",
        False,
        "below-minimum-value",
        history={"known_destination": False},
        changes={"amount": 49_999},
    ),
    case("unfamiliar_destination", False, "destination-known"),
    case(
        "amount_above_customer_profile",
        False,
        "one-cent-below-five-times-average",
        changes={"amount": 99_999},
    ),
    case("amount_above_customer_profile", True, "exactly-five-times-average", changes={"amount": 100_000}),
    case(
        "amount_above_customer_profile",
        True,
        "one-cent-above-five-times-average",
        changes={"amount": 100_001},
    ),
    case(
        "amount_above_customer_profile",
        False,
        "no-eligible-value-reference",
        history={**NO_REFERENCE, "registered_count": 1},
        changes={"amount": 100_000},
    ),
    case("unfamiliar_device", True, "unknown-with-three-approvals", history={"known_device": False}),
    case(
        "unfamiliar_device",
        False,
        "fewer-than-three-approvals",
        history={"known_device": False, "approved_count": 2},
    ),
    case(
        "unfamiliar_device",
        False,
        "below-minimum-value",
        history={"known_device": False},
        changes={"amount": 49_999},
    ),
    case("unfamiliar_device", False, "device-known"),
    case("shared_device", False, "two-owners-including-current", history={"device_other_owners": 1}),
    case("shared_device", True, "three-owners-including-current", history={"device_other_owners": 2}),
    case("shared_device", True, "four-owners-including-current", history={"device_other_owners": 3}),
    case(
        "multiple_devices",
        False,
        "two-devices-including-current",
        history={"known_device": False, "payer_other_devices": 1},
    ),
    case(
        "multiple_devices",
        True,
        "three-devices-including-current",
        history={"known_device": False, "payer_other_devices": 2},
    ),
    case("multiple_devices", False, "known-device-excluded", history={"payer_other_devices": 2}),
    case(
        "unusual_night_app",
        True,
        "night-app-and-new-device",
        history={"known_device": False},
        changes={"night": True},
    ),
    case(
        "unusual_night_app",
        True,
        "night-app-and-new-destination",
        history={"known_destination": False},
        changes={"night": True},
    ),
    case("unusual_night_app", False, "daytime-excluded", history={"known_device": False}),
    case(
        "unusual_night_app",
        False,
        "habitual-night-use-excluded",
        history={"known_device": False, "approved_night_count": 1},
        changes={"night": True},
    ),
    case(
        "unusual_night_app",
        False,
        "fewer-than-three-approvals",
        history={"known_device": False, "approved_count": 2},
        changes={"night": True},
    ),
    case(
        "unusual_night_app",
        False,
        "below-minimum-value",
        history={"known_device": False},
        changes={"night": True, "amount": 49_999},
    ),
    case(
        "unusual_night_app",
        False,
        "internet-banking-excluded",
        history={"known_device": False},
        changes={"night": True, "channel": "internet_banking"},
    ),
    case("unusual_night_app", False, "no-novelty-excluded", changes={"night": True}),
    case(
        "possible_duplicate_payment",
        True,
        "previous-payment-at-window-boundary",
        history={"duplicate_transaction_id": "prior-pix", "duplicate_elapsed_seconds": 120},
    ),
    case("possible_duplicate_payment", False, "no-previous-eligible-payment"),
]


def transaction_for(payload, changes):
    payload["amount"] = changes.get("amount", 50_000)
    if changes.get("night"):
        payload["transaction_date"] = "2026-10-17T23:00:00-03:00"
    at = datetime.fromisoformat(payload["transaction_date"])
    for side in ("source", "destination"):
        key = f"{side}_age_seconds"
        if key in changes:
            payload[f"{side}_account"]["opening_date"] = (at - timedelta(seconds=changes[key])).isoformat()
    payload["source"]["channel"] = changes.get("channel", "app")
    return PixTransactionCreate.model_validate(payload)


@pytest.mark.parametrize("code,active,history,changes", RULE_CASES)
def test_each_rule_activation_boundary_and_exclusions(payload, code, active, history, changes):
    status, evidence = DecisionEngine(POLICY).evaluate(
        transaction_for(payload, changes), replace(BASE_HISTORY, **history)
    )
    matches = {rule["code"]: rule for rule in evidence["triggered_rules"]}
    assert (code in matches) is active
    if active:
        rule = matches[code]
        assert rule["weight"] == getattr(POLICY.scoring.weights, code)
        assert rule["risk_factor"] == getattr(POLICY.scoring.rule_factors, code)
        assert rule["hard_limit"] is (code in {"velocity_above_limit", "accumulated_amount_above_limit"})
        assert rule["observed"] is not None
        assert rule["threshold"] is not None
        if rule["hard_limit"]:
            assert status == "rejected"
            assert evidence["decision_source"] == "hard_limit"


def test_every_configured_rule_has_positive_and_negative_audit_cases():
    expected = set(asdict(POLICY.scoring.weights))
    for active in (False, True):
        assert {entry.values[0] for entry in RULE_CASES if entry.values[1] is active} == expected
