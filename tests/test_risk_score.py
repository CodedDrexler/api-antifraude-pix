"""Observable scoring behavior through HTTP with isolated registered histories."""

from datetime import datetime, timedelta

from conftest import new_transaction
from test_pix import post, seed_profile


def score(api, payload):
    decision = post(api, payload)
    m = decision["metadata"]
    assert type(m["risk_score"]) is int and 0 <= m["risk_score"] <= 100
    assert m["policy"]["version"] == "pix-score-v6"
    assert m["score_semantics"] == "heuristic_not_probability"
    assert sum(rule["weight"] for rule in m["triggered_rules"]) == m["raw_score"]
    assert sum(f["score"] for f in m["risk_factors"]) == m["risk_factors_sum"]
    assert m["risk_factors_sum"] - m["score_cap_reduction"] == m["risk_score"]
    for factor in m["risk_factors"]:
        group = factor["name"]
        values = m["group_scores"][group]
        assert factor["score"] == values["score"] <= values["cap"]
        assert factor["weight"] == m["policy"]["scoring"]["factor_weights"][group]
        assert set(factor["rules"]) == {r["code"] for r in m["triggered_rules"] if r["risk_factor"] == group}
        assert sum(r["contribution"] for r in m["triggered_rules"] if r["group"] == group) == values["score"]
    return decision


def test_first_pix_requests_two_factor_and_saves_explanation(api, payload):
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 30
    assert decision["status"] == "two_factor_required"
    assert decision["metadata"]["decision_source"] == "first_transaction"
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == decision
    assert post(api, payload) == decision


def test_normal_value_after_first_registration_has_zero_score(api, payload):
    seed_profile(api, payload, 1)
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 0
    assert decision["metadata"]["risk_factors"] == []
    assert decision["metadata"]["risk_factors_sum"] == 0
    assert decision["status"] == "approved"


def test_weak_device_signal_alone_approves(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "new-device-" + payload["id"]
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 20
    assert decision["status"] == "approved"


def test_two_weak_groups_combine_into_two_factor(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "new-device-" + payload["id"]
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
    assert decision["metadata"]["raw_score"] == 30
    assert decision["metadata"]["risk_score"] == 25
    assert decision["status"] == "approved"


def test_high_profile_signal_alone_requires_two_factor(api, payload):
    seed_profile(api, payload, 1, amount=1000)
    payload["amount"] = 5000
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 80
    assert decision["metadata"]["risk_level"] == "high"
    assert decision["metadata"]["hard_limits"] == []
    assert decision["status"] == "two_factor_required"


def test_high_profile_plus_new_account_rejects(api, payload):
    seed_profile(api, payload, 1, amount=1000)
    payload["amount"] = 5000
    at = datetime.fromisoformat(payload["transaction_date"])
    payload["source_account"]["opening_date"] = (at - timedelta(hours=6)).isoformat()
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 95
    assert decision["metadata"]["decision_source"] == "risk_score"
    assert decision["status"] == "rejected"


def test_factor_sum_can_exceed_final_score_cap(api, payload):
    seed_profile(api, payload, 3, amount=10_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "new-device-" + payload["id"]
    payload["destination_account"]["account_number"] = "unfamiliar"
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 100
    assert decision["metadata"]["risk_factors_sum"] == 140
    assert decision["metadata"]["score_cap_reduction"] == 40
    assert decision["status"] == "rejected"


def test_activity_group_cap_preserves_all_hard_reasons(api, payload):
    for index in range(5):
        post(api, new_transaction(payload, amount=600_000 + index))
    decision = score(api, payload)
    assert decision["metadata"]["risk_score"] == 80
    assert set(decision["metadata"]["hard_limits"]) == {
        "velocity_above_limit",
        "accumulated_amount_above_limit",
    }
    assert decision["metadata"]["group_scores"]["activity"]["raw_score"] == 160
