from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from conftest import new_transaction
from test_pix import post, seed_profile

from src.constants import Policy, UntrustPolicy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import PixController
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import History
from src.schemas.pix import PixTransactionCreate


def baseline(payload, amount=5000):
    payload["amount"] = amount
    return DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 3, 3000, True, True, 3, 3000),
    )


def test_increment_uses_current_rule_evidence_and_never_account_score(payload):
    status, metadata = baseline(payload)
    status, untrust, notification = assess_untrust(status, metadata, UntrustHistory(20, 1), UntrustPolicy())
    assert status == "two_factor_required"
    assert untrust["increment"] == 20
    assert untrust["score_before"] == 20
    assert untrust["score"] == 40
    assert notification["required"] is False
    assert metadata["risk_score"] == 80  # Account score is separate; no double counting.


@pytest.mark.parametrize(
    "points,events,action,notify",
    [
        (0, 0, "none", False),
        (39, 2, "none", False),
        (40, 2, "two_factor_required", False),
        (59, 3, "two_factor_required", False),
        (60, 3, "two_factor_required", True),
        (79, 4, "two_factor_required", True),
        (80, 4, "two_factor_required", True),
        (100, 1, "two_factor_required", True),
    ],
)
def test_account_thresholds_and_repeated_evidence_guard(payload, points, events, action, notify):
    status, metadata = baseline(payload, amount=1000)
    status, untrust, notification = assess_untrust(
        status, metadata, UntrustHistory(points, events), UntrustPolicy()
    )
    assert untrust["action"] == action
    assert untrust["increment"] == 0
    assert notification["required"] is notify
    assert notification["status"] == ("indicated_only" if notify else "not_required")
    assert status == ("approved" if action == "none" else action)


def test_active_block_does_not_refresh_itself_even_on_velocity_risk(payload):
    status, metadata = baseline(payload)
    metadata["hard_limits"] = ["velocity_above_limit"]
    status, untrust, _ = assess_untrust("rejected", metadata, UntrustHistory(100, 5), UntrustPolicy())
    assert status == "rejected"
    assert untrust["increment"] == 0
    assert untrust["increment_suppressed_by_active_restriction"] is True
    assert untrust["score"] == 100


def test_first_transaction_and_account_age_alone_do_not_build_untrust(payload):
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, 0, False, False),
    )
    assert metadata["risk_score"] == 45
    _, untrust, _ = assess_untrust(status, metadata, UntrustHistory(), UntrustPolicy())
    assert untrust["increment"] == 0
    assert untrust["eligible_rules"] == []


def test_single_low_risk_novelty_does_not_accumulate(payload):
    _, metadata = baseline(payload, amount=1000)
    metadata.update(
        risk_score=20,
        triggered_rules=[
            {
                "risk_factor": "device",
                "contribution": 20,
                "code": "unfamiliar_device",
            }
        ],
    )
    assert assess_untrust("approved", metadata, UntrustHistory(), UntrustPolicy())[1]["increment"] == 0


def test_disabled_policy_and_existing_hard_rejection_are_preserved(payload):
    _, metadata = baseline(payload)
    _, untrust, notice = assess_untrust(
        "approved", metadata, UntrustHistory(100, 10), replace(UntrustPolicy(), enabled=False)
    )
    assert untrust["score"] == 0 and untrust["increment"] == 0
    assert notice["required"] is False
    status, _, _ = assess_untrust("rejected", metadata, UntrustHistory(), UntrustPolicy())
    assert status == "rejected"


def test_notification_indicates_threshold_crossing_without_claiming_delivery(payload):
    status, metadata = baseline(payload)
    _, untrust, notice = assess_untrust(status, metadata, UntrustHistory(40, 2), UntrustPolicy())
    assert untrust["score"] == 60
    assert notice["threshold_crossed"] is True
    assert notice["status"] == "indicated_only"
    _, _, repeated = assess_untrust(status, metadata, UntrustHistory(60, 3), UntrustPolicy())
    assert repeated["required"] is True and repeated["threshold_crossed"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": 1},
        {"window_hours": 0},
        {"score_divisor": True},
        {"notification_threshold": 101},
        {"rejection_threshold": 60},
        {"maximum_increment": 26},
        {"minimum_rejection_events": 1},
    ],
)
def test_invalid_untrust_policy_fails_startup(changes):
    with pytest.raises(ValueError):
        replace(UntrustPolicy(), **changes)


def test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score(api, payload):
    seed_profile(api, payload, 1, amount=1000)
    decisions = [post(api, new_transaction(payload, amount=5000)) for _ in range(4)]
    assert [r["metadata"]["account_untrust"]["score"] for r in decisions] == [20, 40, 60, 80]
    assert decisions[2]["metadata"]["bank_notification"]["required"] is True
    normal = post(api, payload)
    assert normal["metadata"]["risk_score"] == 0
    assert normal["status"] == "two_factor_required"
    assert normal["metadata"]["decision_source"] == "account_untrust"
    assert normal["metadata"]["account_untrust"]["increment"] == 0
    assert post(api, payload) == normal
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == normal


def test_untrust_is_per_account_not_all_accounts_of_same_owner(api, payload):
    seed_profile(api, payload, 1, amount=1000)
    for _ in range(2):
        post(api, new_transaction(payload, amount=5000))
    other_account = new_transaction(payload)
    other_account["source_account"]["account_number"] = "other-account"
    result = post(api, other_account)
    assert result["metadata"]["account_untrust"]["score"] == 0
    original = post(api, payload)
    assert original["status"] == "two_factor_required"
    assert original["metadata"]["account_untrust"]["score"] == 40


def test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points(
    api, payload
):
    seed_profile(api, payload, 1)
    post(api, new_transaction(payload, amount=5000))
    invalid = new_transaction(payload, amount=-1)
    assert api("POST", "/pix/transaction", invalid)[0] == 400
    payload["source_account"]["opening_date"] = "2019-01-01T00:00:00Z"
    result = post(api, payload)
    assert result["metadata"]["account_untrust"]["score"] == 20
    assert result["metadata"]["account_untrust"]["risk_events"] == 1


def test_concurrent_account_attempts_cannot_lose_increments(api, payload):
    seed_profile(api, payload, 1)
    candidates = [new_transaction(payload, amount=5000) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda body: post(api, body), candidates))
    assert sorted(r["metadata"]["account_untrust"]["score"] for r in results) == [20, 40, 60, 80]
    assert sum(r["metadata"]["bank_notification"]["threshold_crossed"] for r in results) == 1


def test_server_clock_not_caller_event_time_is_passed_to_account_history(payload):
    session = Mock()
    controller = PixController(session, Policy())
    repository = Mock()
    repository.get.return_value = None
    repository.history.return_value = History(0, 0, 3, 3000, True, True, 3, 3000)
    repository.untrust_history.return_value = UntrustHistory(40, 2)
    repository.create.side_effect = lambda **values: PixAnalysis(**values)
    controller.repository = repository
    payload["transaction_date"] = "2020-10-17T14:00:00Z"
    payload["destination_account"]["opening_date"] = "2020-10-10T12:00:00Z"
    before = datetime.now().astimezone() - timedelta(seconds=1)
    result = controller.analyze(PixTransactionCreate.model_validate(payload))
    observed = repository.untrust_history.call_args.args[1]
    assert observed >= before
    assert result.status == "two_factor_required"


def test_explicit_opt_in_can_block_with_repeated_evidence_but_never_relaxes_baseline(payload):
    status, metadata = baseline(payload, amount=1000)
    assert status == "approved"
    status, untrust, _ = assess_untrust(
        status, metadata, UntrustHistory(80, 4), replace(UntrustPolicy(), rejection_enabled=True)
    )
    assert status == "rejected"
    assert untrust["action"] == "rejected" and untrust["decision_override"] is True


def test_expired_history_removes_restriction_without_approval_resetting_existing_history(payload):
    status, metadata = baseline(payload, amount=1000)
    assert (
        assess_untrust(status, metadata, UntrustHistory(60, 3), UntrustPolicy())[0] == "two_factor_required"
    )
    status, untrust, notice = assess_untrust(status, metadata, UntrustHistory(), UntrustPolicy())
    assert status == "approved"
    assert untrust["score"] == 0 and notice["required"] is False
