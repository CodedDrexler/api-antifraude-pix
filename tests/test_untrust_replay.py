"""Differential tests: the offline evaluator must agree with PostgreSQL/controller."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from scripts.evaluate_untrust import evaluate, replay
from src.constants import Policy
from src.controllers.pix_controller import PixController
from src.errors.pix_errors import TransactionConflict
from src.schemas.pix import PixTransactionCreate


def sequence(payload, scenario):
    at = datetime.fromisoformat(payload["transaction_date"])

    def event(name, seconds, amount=20_000):
        row = deepcopy(payload)
        row.update(
            id=payload["id"] + name,
            amount=amount,
            transaction_date=(at - timedelta(seconds=seconds)).isoformat(),
        )
        return row

    records = [event(f"-profile-{index}", hours * 3600) for index, hours in enumerate((48, 47, 46, 45))]
    candidate = event("-candidate", 0)
    if scenario.startswith("duplicate-"):
        gap = {
            "duplicate-inside": 119.999999,
            "duplicate-boundary": 120,
            "duplicate-outside": 120.000001,
            "duplicate-same-time": 0,
        }[scenario]
        previous = event("-z-prior", gap)
        candidate["id"] = payload["id"] + "-a-candidate"  # Lexically before the prior ID.
        records.append(previous)
    elif scenario in {"profile-below", "profile-at"}:
        candidate["amount"] = 99_999 if scenario == "profile-below" else 100_000
    elif scenario == "profile-and-recipient":
        candidate["amount"] = 100_000
        candidate["destination_account"]["account_number"] = "unknown-destination"
    elif scenario == "device-and-recipient":
        candidate["amount"] = 50_000
        candidate["source"]["device_id"] = "unknown-" + payload["id"]
        candidate["destination_account"]["account_number"] = "unknown-destination"
    elif scenario == "shared-device":
        for index in range(2):
            row = event(f"-other-owner-{index}", (index + 1) * 3600)
            owner = int(payload["source_account"]["owner"]["document_number"])
            row["source_account"]["owner"]["document_number"] = f"{(owner + index + 1) % 10**11:011d}"
            records.append(row)
    elif scenario.startswith("untrust-"):
        first_age = {
            "untrust-active": 86400 - 0.000001,
            "untrust-expired": 86400,
            "untrust-outside": 86400 + 0.000001,
        }[scenario]
        records.extend([event("-risk-one", first_age, 100_000), event("-risk-two", 3600, 100_000)])
    elif scenario == "idempotent":
        candidate = deepcopy(records[-1])
    else:
        raise AssertionError(scenario)
    records.sort(key=lambda row: datetime.fromisoformat(row["transaction_date"]))
    return candidate, records


@pytest.mark.parametrize(
    "scenario,expected,score,account_score",
    [
        ("duplicate-inside", "two_factor_required", 30, 0),
        ("duplicate-boundary", "two_factor_required", 30, 0),
        ("duplicate-outside", "approved", 0, 0),
        ("duplicate-same-time", "two_factor_required", 30, 0),
        ("profile-below", "approved", 0, 0),
        ("profile-at", "two_factor_required", 80, 20),
        ("profile-and-recipient", "rejected", 95, 20),
        ("device-and-recipient", "two_factor_required", 35, 5),
        ("shared-device", "two_factor_required", 30, 8),
        ("untrust-active", "two_factor_required", 0, 40),
        ("untrust-expired", "approved", 0, 20),
        ("untrust-outside", "approved", 0, 20),
        ("idempotent", "approved", 0, 0),
    ],
)
def test_replay_agrees_with_persisted_decisions_at_each_step(
    database_engine, payload, monkeypatch, scenario, expected, score, account_score
):
    candidate, records = sequence(payload, scenario)

    class Clock:
        current = None

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    monkeypatch.setattr("src.controllers.pix_controller.datetime", Clock)
    policy = Policy()
    with Session(database_engine) as session:
        controller = PixController(session, policy)
        previous = []
        for body in [*records, candidate]:
            tx = PixTransactionCreate.model_validate(body)
            Clock.current = tx.transaction_date
            actual = controller.analyze(tx)
            simulated = replay(body, previous, policy, include_details=True)
            assert simulated[0] == actual.status
            for key, value in simulated[3].items():
                observed = actual.metadata[key]
                if key == "policy":
                    # The controller records the disabled GNN's policy separately.
                    observed = {
                        name: item for name, item in observed.items() if name not in {"gnn", "gnn_v2"}
                    }
                assert observed == value, (scenario, body["id"], key)
            previous.append(body)
        assert actual.status == expected
        assert actual.metadata["risk_score"] == score
        assert actual.metadata["account_untrust"]["score"] == account_score
        assert controller.get_analysis(candidate["id"]) == actual
        # Repeated reads/retries never add another evidence event.
        assert controller.analyze(PixTransactionCreate.model_validate(candidate)) == actual


def test_replay_rejects_conflicting_ids_instead_of_recounting_risk(payload):
    changed = deepcopy(payload)
    changed["amount"] += 1
    with pytest.raises(TransactionConflict):
        replay(changed, [payload], Policy())


@pytest.mark.parametrize("fraud,label", [(0, "synthetic_legitimate"), (1, "synthetic_fraud")])
def test_comparison_report_attributes_the_same_pix_change_to_its_account_history(
    payload, monkeypatch, fraud, label
):
    candidate, records = sequence(payload, "untrust-active")
    monkeypatch.setattr("scripts.evaluate_untrust.scenario", lambda *_: (candidate, records, fraud, "paired"))
    report = evaluate("test", 1, Policy())
    assert report["decision_transitions"][label] == {"approved -> two_factor_required": 1}
    assert report["counts"]["changed_decisions"] == 1
    assert report["counts"]["additional_fraud_challenges"] == fraud
    assert report["counts"]["additional_legitimate_challenges"] == 1 - fraud
    example = report["changed_examples"][0]
    assert example["decision_source"] == "account_untrust"
    assert example["baseline_risk_score"] == example["untrust_risk_score"] == 0
    assert example["account_score_before"] == example["account_score"] == 40
    assert example["current_increment"] == 0
    assert example["transaction_evidence_changed"] is False
    assert example["label"] == label
