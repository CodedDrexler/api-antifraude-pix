"""Observable scoring behavior through HTTP, with synthetic and isolated histories."""

from datetime import datetime, timedelta

from conftest import new_transaction
from test_pix import post, seed_profile


def score(api, payload):
    decision = post(api, payload)
    m = decision["metadata"]
    assert type(m["risk_score"]) is int and 0 <= m["risk_score"] <= 100
    assert m["policy"]["version"] == "pix-score-v2"
    assert m["score_semantics"] == "heuristic_not_probability"
    assert sum(rule["weight"] for rule in m["triggered_rules"]) == m["raw_score"]
    assert (
        sum(rule["contribution"] for rule in m["triggered_rules"]) - m["score_cap_reduction"]
        == m["risk_score"]
    )
    for group, values in m["group_scores"].items():
        assert values["score"] <= values["cap"]
        assert (
            sum(rule["contribution"] for rule in m["triggered_rules"] if rule["group"] == group)
            == values["score"]
        )
    return decision


def test_zero_score_cold_start_and_saved_explanation(api, payload):
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 0
    assert decision["status"] == "approved"
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == decision
    assert post(api, payload) == decision


def test_threshold_30_requests_two_factor(api, payload):
    payload["amount"] = 100_000
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 30
    assert decision["metadata"]["risk_level"] == "elevated"
    assert decision["status"] == "two_factor_required"


def test_weak_device_signal_alone_approves(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "new-device"
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 20
    assert decision["status"] == "approved"


def test_two_weak_groups_combine_into_two_factor(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "new-device"
    payload["destination_account"]["account_number"] = "unfamiliar"
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 35
    assert decision["status"] == "two_factor_required"


def test_related_counterparty_signals_are_capped(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["destination_account"]["account_number"] = "unfamiliar"
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    decision = score(api, payload)
    m = decision["metadata"]
    assert m["raw_score"] == 30
    assert m["risk_score"] == 25
    assert m["risk_group_count"] == 1
    assert decision["status"] == "approved"


def test_exact_80_rejects_combined_groups_without_hard_limit(api, payload):
    seed_profile(api, payload, 5, amount=10_000)
    payload["amount"] = 100_000
    payload["destination_account"]["account_number"] = "unfamiliar"
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 80  # 30 exposure + 25 counterparty + 25 profile
    assert decision["metadata"]["hard_limits"] == []
    assert decision["metadata"]["decision_source"] == "risk_score"
    assert decision["status"] == "rejected"


def test_score_75_requires_two_factor(api, payload):
    seed_profile(api, payload, 5, amount=10_000)
    payload["amount"] = 100_000
    payload["source"]["device_id"] = "new-device"
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 75
    assert decision["status"] == "two_factor_required"


def test_score_is_capped_at_100(api, payload):
    seed_profile(api, payload, 5, amount=10_000)
    payload["amount"] = 200_000
    payload["source"]["device_id"] = "new-device"
    payload["destination_account"]["account_number"] = "unfamiliar"
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    at = datetime.fromisoformat(payload["transaction_date"])
    payload["source_account"]["opening_date"] = (at - timedelta(hours=6)).isoformat()
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 100
    assert decision["metadata"]["score_cap_reduction"] == 15
    assert decision["status"] == "rejected"


def test_hard_amount_does_not_double_count_moderate_amount(api, payload):
    payload["amount"] = 2_000_000
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 80
    assert decision["metadata"]["raw_score"] == 110
    assert decision["metadata"]["decision_source"] == "hard_limit"
    moderate = next(
        rule
        for rule in decision["metadata"]["triggered_rules"]
        if rule["code"] == "amount_requires_two_factor"
    )
    assert moderate["contribution"] == 0


def test_activity_group_cap_preserves_all_hard_reasons(api, payload):
    for _ in range(5):
        post(api, new_transaction(payload, amount=600_000))
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 80
    assert set(decision["metadata"]["hard_limits"]) == {
        "velocity_above_limit",
        "accumulated_amount_above_limit",
    }
    assert decision["metadata"]["group_scores"]["activity"]["raw_score"] == 160


def test_cold_start_does_not_create_unknown_device_or_recipient_risk(api, payload):
    payload["amount"] = 50_000
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 15
    assert "unfamiliar_device" not in decision["metadata"]["reasons"]
    assert "unfamiliar_destination" not in decision["metadata"]["reasons"]
