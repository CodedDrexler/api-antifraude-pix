"""Entity identity, temporal control, independent evidence and graph score integration."""

import copy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.dtos.pix_dto import PixAnalysisDTO
from src.entity_risk import (
    ConfirmedIncident,
    CorporateLink,
    EntityRegistry,
    EntityRiskService,
    OwnEvidence,
    combine_entity_risk,
)
from src.gnn.service import combine_graph_risk
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate

NOW = datetime(2026, 10, 17, 15, tzinfo=timezone.utc)
PERSON = "12345678901"


def company(index):
    return f"{10_000_000 + index:08d}000199"


def link(index, **changes):
    values = dict(
        link_id=f"link-{index}",
        person_or_company=PERSON,
        company=company(index),
        role="controller",
        verified=True,
        valid_from=NOW - timedelta(days=90),
        known_at=NOW - timedelta(days=80),
        reference="synthetic-verified-registry",
    )
    values.update(changes)
    return CorporateLink(**values)


def incident(index, **changes):
    values = dict(
        incident_id=f"incident-{index}",
        documents=(company(index),),
        severity=90,
        occurred_at=NOW - timedelta(days=2),
        known_at=NOW - timedelta(days=1),
        reference="synthetic-confirmed-outcome",
    )
    values.update(changes)
    return ConfirmedIncident(**values)


def registry(size=10, **changes):
    values = dict(
        version="synthetic-v1",
        links=tuple(link(i) for i in range(size)),
        incidents=tuple(incident(i) for i in range(size)),
    )
    values.update(changes)
    return EntityRegistry(**values)


def assessment(data=None, mode="contribute", **changes):
    return EntityRiskService(mode, registry=data).assess(PERSON, NOW, [], **changes)


def baseline(payload):
    return DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 3, True, True, 3, payload["amount"] * 3),
    )


def test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct(payload):
    result = assessment(registry())
    assert result["own_entity"]["score"] == 0
    exposure = result["relationships"]
    assert exposure["confirmed_incidents"] == exposure["strong_confirmed_incidents"] == 10
    assert exposure["related_company_roots_with_evidence"] == 10
    assert exposure["exposure_score"] == 100
    assert result["proposed_action"] == "two_factor_required"
    status, metadata = baseline(payload)
    assert status == "approved" and metadata["risk_score"] == 0
    final, enriched = combine_entity_risk(status, metadata, result)
    assert final == "two_factor_required" and enriched["risk_score"] == 20
    assert enriched["decision_source"] == "entity_risk"
    assert enriched["entity_risk"]["decision_override"]
    assert metadata["risk_score"] == 0 and "entity_risk" not in metadata


def test_new_company_inherits_exposure_through_verified_common_controller():
    data = registry()
    newcomer = company(50)
    data = data.model_copy(update={"links": (*data.links, link(50, valid_from=NOW - timedelta(days=1)))})
    result = EntityRiskService("contribute", registry=data).assess(newcomer, NOW, [])
    assert result["own_entity"]["score"] == 0
    assert result["relationships"]["strong_confirmed_incidents"] == 10
    assert all(len(event["path"]) == 2 for event in result["relationships"]["evidence"])
    assert result["proposed_action"] == "two_factor_required"


def test_multiple_company_levels_and_cycles_do_not_duplicate_events():
    holding = company(50)
    links = (
        link(50),
        link(1, person_or_company=holding),
        link(99, person_or_company=company(1), company=holding),
    )
    result = assessment(registry(links=links, incidents=(incident(1),)))
    assert result["relationships"]["confirmed_incidents"] == 1
    assert result["relationships"]["strong_confirmed_incidents"] == 1
    assert result["proposed_action"] == "none"


def test_same_incident_across_ten_cnpjs_is_one_independent_evidence():
    data = registry(incidents=(incident(1, documents=tuple(company(i) for i in range(10))),))
    result = assessment(data)
    assert result["relationships"]["related_company_roots_with_evidence"] == 10
    assert result["relationships"]["confirmed_incidents"] == 1
    assert result["relationships"]["exposure_score"] == 90
    assert result["proposed_action"] == "none"


def test_company_branches_are_one_company_root_not_ten_companies():
    branches = tuple(f"10000000{i:04d}99" for i in range(1, 11))
    data = registry(
        links=tuple(link(i, company=doc) for i, doc in enumerate(branches)),
        incidents=(incident(1, documents=branches),),
    )
    result = assessment(data)
    assert result["relationships"]["related_company_roots_with_evidence"] == 1
    assert result["relationships"]["confirmed_incidents"] == 1


@pytest.mark.parametrize("role,maximum", [("accountant", 0), ("minority_partner", 18), ("administrator", 45)])
def test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override(role, maximum):
    data = registry(links=tuple(link(i, role=role) for i in range(10)))
    result = assessment(data)
    assert result["relationships"]["exposure_score"] <= maximum
    assert result["relationships"]["strong_confirmed_incidents"] == 0
    assert result["proposed_action"] == "none"


@pytest.mark.parametrize(
    "changes",
    [
        {"verified": False},
        {"known_at": NOW + timedelta(hours=1)},
        {"valid_from": NOW + timedelta(hours=1)},
        {"valid_until": NOW - timedelta(hours=1)},
        {"valid_from": NOW - timedelta(days=1)},  # Joined after the incident.
    ],
)
def test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud(changes):
    result = assessment(registry(1, links=(link(0, **changes),)))
    assert result["relationships"]["confirmed_incidents"] == 0
    assert result["relationships"]["exposure_score"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"known_at": NOW + timedelta(hours=1)},
        {"expires_at": NOW},
        {"revoked_at": NOW},
    ],
)
def test_incident_must_be_known_active_and_not_revoked_at_decision(changes):
    result = assessment(registry(1, incidents=(incident(0, **changes),)))
    assert result["relationships"]["confirmed_incidents"] == 0


def test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation():
    result = assessment(
        registry(
            1,
            incidents=(incident(0, occurred_at=NOW - timedelta(days=60), known_at=NOW - timedelta(days=59)),),
        )
    )
    assert result["relationships"]["confirmed_incidents"] == 1


def test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores():
    evidence = [
        OwnEvidence("a", PERSON, NOW - timedelta(hours=2), 20, "account-a"),
        OwnEvidence("b", PERSON, NOW - timedelta(hours=1), 20, "account-b"),
    ]
    service = EntityRiskService("contribute")
    result = service.assess(PERSON, NOW, evidence + evidence)
    assert result["own_entity"]["score"] == 40
    assert result["own_entity"]["risk_events"] == 2
    assert result["own_entity"]["accounts_with_evidence"] == 2
    assert result["proposed_action"] == "two_factor_required"
    assert result["relationships"]["exposure_score"] == result["proposed_points"] == 0
    assert result["registry_status"] == "not_configured"


def test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded():
    evidence = [
        OwnEvidence("old", PERSON, NOW - timedelta(hours=24), 25),
        OwnEvidence("future", PERSON, NOW + timedelta(seconds=1), 25),
    ]
    result = EntityRiskService("contribute").assess(PERSON, NOW, evidence, current_increment=20)
    assert result["own_entity"]["score"] == 20
    assert result["own_entity"]["risk_events"] == 1


def test_rule_evidence_from_before_ownership_does_not_create_soft_exposure():
    data = registry(1, links=(link(0, valid_from=NOW - timedelta(minutes=5)),), incidents=())
    evidence = [OwnEvidence("old-owner", company(0), NOW - timedelta(hours=2), 25)]
    result = EntityRiskService("contribute", registry=data).assess(PERSON, NOW, evidence)
    assert result["relationships"]["max_related_untrust"] == 0


def test_clean_companies_do_not_dilute_high_risk_company():
    one = assessment(registry(1))
    many = assessment(registry(50, incidents=(incident(0),)))
    assert one["relationships"]["exposure_score"] == many["relationships"]["exposure_score"] == 90


def test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works():
    result = assessment(registry(), history_truncated=True)
    assert result["own_entity"]["score"] is None
    assert result["own_entity"]["history_status"] == "truncated"
    assert result["proposed_action"] == "two_factor_required"


def test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence():
    data = registry(120)
    result = assessment(data)
    assert result["relationships"]["coverage"] == "truncated"
    assert result["relationships"]["exposure_score"] == 0
    compact = PixAnalysisDTO(key="test", status="approved", metadata={"entity_risk": result}).compact()
    assert compact.metadata["entity_risk"]["relationship_coverage"] == "truncated"
    data = data.model_copy(update={"incidents": (incident(0, documents=(PERSON,)),)})
    assert assessment(data)["proposed_action"] == "two_factor_required"


def test_shadow_preserves_scores_decision_and_account_evidence(payload):
    status, metadata = baseline(payload)
    snapshot = copy.deepcopy(metadata)
    final, enriched = combine_entity_risk(status, metadata, assessment(registry(), mode="shadow"))
    assert final == status
    assert enriched["risk_score"] == metadata["risk_score"] == 0
    assert enriched["policy"]["version"] == metadata["policy"]["version"]
    assert enriched["entity_risk"]["applied_points"] == 0
    assert metadata == snapshot


def test_entity_and_gnn_share_cap_and_cannot_supply_two_graph_rejection_groups(payload):
    status, metadata = baseline(payload)
    graph = {
        "mode": "contribute",
        "status": "scored",
        "gnn_score": 95,
        "proposed_points": 20,
        "threshold": 80,
        "experimental": True,
        "training_data": "synthetic",
    }
    status, metadata = combine_graph_risk(status, metadata, graph)
    _, enriched = combine_entity_risk(status, metadata, assessment(registry()))
    assert enriched["risk_score"] == enriched["group_scores"]["graph"]["score"] == 20
    assert enriched["risk_group_count"] == 1
    assert sum(rule["contribution"] for rule in enriched["triggered_rules"]) == 20
    assert sum(factor["score"] for factor in enriched["risk_factors"]) == 20
    assert enriched["entity_risk"]["applied_points"] == 0
    gnn_rule = next(rule for rule in enriched["triggered_rules"] if rule["code"] == "gnn_relational_pattern")
    assert gnn_rule["contribution"] == enriched["gnn"]["applied_points"] == 20


def test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved(payload):
    status, metadata = baseline(payload)
    metadata["policy"]["scoring"]["factor_weights"]["graph"] = 0
    final, enriched = combine_entity_risk(status, metadata, assessment(registry()))
    assert final == "approved" and enriched["risk_score"] == 0
    final, _ = combine_entity_risk("rejected", metadata, assessment(registry()))
    assert final == "rejected"


def test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields():
    with pytest.raises(ValidationError):
        link(0, person_or_company="***456789**")
    with pytest.raises(ValidationError):
        registry(incidents=(incident(0), incident(0)))
    with pytest.raises(ValidationError):
        link(0, valid_until=NOW - timedelta(days=100))
    with pytest.raises(ValidationError):
        registry(foo="not-an-operator-field")


def test_registry_loading_is_strict_hashed_and_off_is_explicit(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(registry().model_dump_json(), encoding="utf-8")
    service = EntityRiskService("shadow", path)
    assert service.registry_hash and service.assess(PERSON, NOW, [])["registry_status"] == "loaded"
    with pytest.raises(ValueError):
        EntityRiskService("invalid")
    path.write_text('{"version":"invalid","links":[{}]}', encoding="utf-8")
    with pytest.raises(ValidationError):
        EntityRiskService("shadow", path)
    assert EntityRiskService("off").assess(PERSON, NOW, [])["status"] == "disabled"
