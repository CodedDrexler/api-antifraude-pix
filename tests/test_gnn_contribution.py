"""Bounded prototype intervention, artifact binding, SQL feedback and HTTP replay."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from conftest import request
from sqlalchemy.orm import Session

from scripts.false_positive_cases import false_positive_scenario
from scripts.validate_temporal_gnn import proposed_status
from src.constants import Policy
from src.controllers.pix_controller import PixController
from src.gnn.contribution import DEFAULT_CONTRIBUTION_POLICY, ContributionPolicy, policy_fingerprint
from src.gnn.temporal_service import ORIGINAL_TEMPORAL_MODEL, TemporalGraphService
from src.risk.attribution import decision_causes
from src.schemas.pix import PixTransactionCreate

ROOT = Path(__file__).resolve().parents[1]


def metadata(service, *, score=100, graph_status="scored", status="approved"):
    return {
        "risk_score": 0,
        "decision_source": "risk_score",
        "risk_factors": [],
        "account_untrust": {"score": 0, "increment": 0},
        "gnn_v2": {
            "status": graph_status,
            "gnn_score": score,
            "model_sha256": service.model.sha256,
            "applied_points": 0,
            "decision_override": False,
        },
    }


@pytest.mark.parametrize(
    "score,expected",
    [
        (75.0976, "approved"),
        (75.0977, "two_factor_required"),
        (75.0978, "two_factor_required"),
        (100, "two_factor_required"),
        (0, "approved"),
    ],
)
def test_frozen_threshold_is_inclusive_and_never_adds_points(score, expected):
    service = TemporalGraphService("contribute")
    evidence = metadata(service, score=score)
    assert service.combine("approved", evidence, Policy()) == expected
    assert evidence["risk_score"] == 0 and evidence["account_untrust"] == {"score": 0, "increment": 0}
    assert evidence["gnn_v2"]["applied_points"] == 0
    assert evidence["gnn_v2"]["decision_override"] == (expected == "two_factor_required")
    if expected == "two_factor_required":
        assert evidence["decision_source"] == "gnn_v2"
        assert decision_causes(evidence, expected) == [
            {"rule_id": "gnn_relational_pattern", "subject": "relationship", "source": "temporal_gnn"}
        ]


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_observation_modes_do_not_intervene_even_with_maximum_score(mode):
    service = TemporalGraphService(mode)
    evidence = metadata(TemporalGraphService())
    assert service.combine("approved", evidence, Policy()) == "approved"
    assert evidence["gnn_v2"]["decision_override"] is False


@pytest.mark.parametrize("status", ["rejected", "two_factor_required"])
@pytest.mark.parametrize(
    "source", ["hard_limit", "risk_score", "account_untrust", "entity_risk", "first_transaction"]
)
def test_contribution_preserves_every_existing_restriction_and_its_cause(status, source):
    service = TemporalGraphService("contribute")
    evidence = metadata(service)
    evidence["decision_source"] = source
    assert service.combine(status, evidence, Policy()) == status
    assert evidence["decision_source"] == source
    assert evidence["gnn_v2"]["decision_override"] is False


@pytest.mark.parametrize(
    "graph_status",
    [
        "insufficient_history",
        "inference_failed",
        "history_truncated",
        "neighborhood_truncated",
        "own_evidence_truncated",
        "unavailable",
        "disabled",
    ],
)
def test_abstention_cannot_generate_a_restriction(graph_status):
    service = TemporalGraphService("contribute")
    evidence = metadata(service, graph_status=graph_status, score=None)
    assert service.combine("approved", evidence, Policy()) == "approved"
    assert evidence["gnn_v2"]["decision_override"] is False


@pytest.mark.parametrize(
    "change", [{"version": "changed"}, {"no_history_min_amount": 60_000}, {"profile_multiplier": 6}]
)
def test_policy_change_disables_graph_contribution_until_revalidated(change):
    service = TemporalGraphService("contribute")
    evidence = metadata(service)
    assert service.combine("approved", evidence, replace(Policy(), **change)) == "approved"
    assert evidence["gnn_v2"]["contribution_status"] == "baseline_policy_mismatch"


def test_old_model_can_still_observe_but_cannot_use_new_models_cut():
    service = TemporalGraphService("contribute", ORIGINAL_TEMPORAL_MODEL)
    evidence = metadata(service)
    assert service.combine("approved", evidence, Policy()) == "approved"
    assert evidence["gnn_v2"]["contribution_status"] == "model_mismatch"


@pytest.mark.parametrize("value", [None, [], {}, {"version": "unknown"}])
def test_missing_or_invalid_manifest_does_not_disable_rules_or_allow_ungated_contribution(tmp_path, value):
    path = tmp_path / "policy.json"
    if value is not None:
        path.write_text(json.dumps(value))
    service = TemporalGraphService("contribute", contribution_path=path)
    assert service.enabled and service.contribution is None
    evidence = metadata(service)
    assert service.combine("approved", evidence, Policy()) == "approved"
    assert evidence["gnn_v2"]["contribution_status"] == "policy_unavailable"


@pytest.mark.parametrize("value", [0, -1, 2, True, "0.75", float("nan"), float("inf")])
def test_manifest_rejects_invalid_thresholds(tmp_path, value):
    data = json.loads(DEFAULT_CONTRIBUTION_POLICY.read_text())
    data["threshold"] = value
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        ContributionPolicy.from_file(path)


def test_runtime_manifest_is_exactly_the_frozen_calibration_and_matches_full_baseline_policy():
    manifest = ContributionPolicy.from_file(DEFAULT_CONTRIBUTION_POLICY)
    directory = ROOT / "models/false-positive-v1/conservative"
    frozen = json.loads((directory / "frozen-thresholds.json").read_text())
    assert manifest.threshold == frozen["thresholds"]["candidate-42/score_only_2fa/confidence_budget"]
    assert manifest.model_sha256 == frozen["models"]["candidate-42"]
    assert (
        manifest.validation_report_sha256
        == hashlib.sha256((directory / "evaluation.metrics.json").read_bytes()).hexdigest()
    )
    assert manifest.baseline_policy_sha256 == policy_fingerprint(
        Policy.from_file(str(ROOT / "config/risk-policy.json"))
    )


def test_runtime_combination_matches_frozen_experimental_proposal_on_new_histories(database_engine):
    from scripts.validate_temporal_gnn import evaluate_case

    for index, kind in enumerate(
        ("contract_fast_settlement", "contract_risky_senders", "ambiguous_legitimate_repass")
    ):
        candidate, history, label, _ = false_positive_scenario(2_000_000 + index, "test", kind)
        service = TemporalGraphService("contribute")
        row = evaluate_case(database_engine, {42: service}, Policy(), candidate, history, label, kind)
        evidence = metadata(service, score=row["live_scores"]["42"])
        expected = proposed_status(row, 42, "score_only_2fa", service.contribution.threshold)
        assert service.combine(row["baseline_status"], evidence, Policy()) == expected


@pytest.mark.parametrize("kind,label", [("contract_fast_settlement", 0), ("contract_risky_senders", 1)])
def test_live_contribution_uses_real_sql_without_self_reinforcement_and_preserves_replay(
    database_engine, kind, label
):
    candidate, history, _, _ = false_positive_scenario(2_100_001, "test", kind)

    class Clock:
        current = None

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    with database_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            controller = PixController(session, Policy(), temporal_service=TemporalGraphService("contribute"))
            with patch("src.controllers.pix_controller.datetime", Clock):
                for payload in sorted(
                    history, key=lambda row: datetime.fromisoformat(row["transaction_date"])
                ):
                    tx = PixTransactionCreate.model_validate(payload)
                    Clock.current = tx.transaction_date
                    controller.analyze(tx)
                tx = PixTransactionCreate.model_validate(candidate)
                Clock.current = tx.transaction_date
                result = controller.analyze(tx)
                assert result.status == ("two_factor_required" if label else "approved")
                assert result.metadata["risk_score"] == 0
                assert result.metadata["account_untrust"]["increment"] == 0
                assert result.metadata["account_untrust"]["score"] == 0
                graph = result.metadata["gnn_v2"]
                assert graph["decision_override"] == bool(label)
                assert (
                    result.metadata["policy"]["gnn_v2"]["contribution_policy"] == graph["contribution_policy"]
                )
                public = result.to_response(include_details=True).model_dump(exclude_unset=True)
                assert "graph_mode" not in public["metadata"]
                if label:
                    assert "Padrão de risco nas relações entre contas" in public["metadata"]["rules"]
                # Changing mode/policy cannot rewrite a saved decision.
                off = PixController(session, replace(Policy(), version="next-policy"))
                assert off.analyze(tx) == result and off.get_analysis(tx.id) == result
                following = deepcopy(candidate)
                following["id"] += "-following"
                following["transaction_date"] = (tx.transaction_date + timedelta(minutes=3)).isoformat()
                Clock.current = tx.transaction_date + timedelta(minutes=3)
                next_result = controller.analyze(PixTransactionCreate.model_validate(following))
                assert next_result.metadata["account_untrust"]["score"] == 0
                if label:
                    assert (
                        next_result.metadata["profile_transactions"]
                        == result.metadata["profile_transactions"]
                    )
        transaction.rollback()


@pytest.mark.parametrize("kind,label", [("contract_fast_settlement", 0), ("contract_risky_senders", 1)])
def test_http_combined_decision_has_graph_reason_and_immutable_replay(api, kind, label):
    # Fix the amounts so this exercises an otherwise-approved baseline. Random
    # contract scaling can independently trigger the five-times-profile rule.
    candidate, history, _, _ = false_positive_scenario(2_100_001, "test", kind)
    nonce = uuid4().hex
    documents, seen = {}, set()
    for payload in [candidate, *history]:
        payload["id"] += nonce
        payload["source"]["device_id"] += nonce
        for side in ("source_account", "destination_account"):
            account = payload[side]
            if id(account) in seen:
                continue
            seen.add(id(account))
            document = account["owner"]["document_number"]
            documents.setdefault(
                document,
                f"{int(hashlib.sha256((nonce + document).encode()).hexdigest()[:14], 16) % 10**11:011d}",
            )
            account["owner"] = {"document_number": documents[document]}
            account["account_number"] += nonce
    for payload in sorted(history, key=lambda row: datetime.fromisoformat(row["transaction_date"])):
        assert api("POST", "/pix/transaction", payload)[0] == 200
    status, result, _ = api("POST", "/pix/transaction", candidate)
    assert status == 200
    assert result["status"] == ("two_factor_required" if label else "approved")
    assert result["metadata"]["risk_score"] == 0
    assert result["metadata"]["gnn_v2"]["decision_override"] == bool(label)
    assert result["metadata"]["account_untrust"]["increment"] == 0
    public = request("GET", "/pix/transaction/" + candidate["id"], include_details=True)[1]
    if label:
        assert "Padrão de risco nas relações entre contas" in public["metadata"]["rules"]
    assert api("POST", "/pix/transaction", candidate)[1] == result
    assert api("GET", "/pix/transaction/" + candidate["id"])[1] == result
