"""Reproduce entity-risk behavior with explicit synthetic facts, without API/database writes."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.entity_risk import (
    ConfirmedIncident,
    CorporateLink,
    EntityRegistry,
    EntityRiskService,
    OwnEvidence,
    combine_entity_risk,
)
from src.financial_features import PaymentEvidence, financial_features
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate

AT = datetime(2026, 10, 17, 15, tzinfo=timezone.utc)
PERSON = "12345678901"


def synthetic_registry(size=10, role="controller", shared_incident=False):
    documents = [f"{10_000_000 + i:08d}000199" for i in range(size)]
    links = tuple(
        CorporateLink(
            link_id=f"control-{i}",
            person_or_company=PERSON,
            company=doc,
            role=role,
            verified=True,
            valid_from=AT - timedelta(days=90),
            known_at=AT - timedelta(days=80),
            reference="SYNTHETIC-ONLY-control",
        )
        for i, doc in enumerate(documents)
    )
    incidents = tuple(
        ConfirmedIncident(
            incident_id=f"fraud-{i}",
            documents=tuple(documents) if shared_incident else (doc,),
            severity=90,
            occurred_at=AT - timedelta(days=2),
            known_at=AT - timedelta(days=1),
            reference="SYNTHETIC-ONLY-incident",
        )
        for i, doc in enumerate(documents[:1] if shared_incident else documents)
    )
    return EntityRegistry(version="SYNTHETIC-ONLY-ten-companies-v1", links=links, incidents=incidents)


def normal_candidate():
    def account(doc):
        return {
            "participant": "12345678",
            "branch": "0001",
            "account_number": doc,
            "opening_date": "2020-01-01T00:00:00+00:00",
            "owner": {"document_number": doc},
        }

    return PixTransactionCreate.model_validate(
        {
            "id": "synthetic-entity-candidate",
            "amount": 10_000,
            "transaction_date": AT.isoformat(),
            "source_account": account(PERSON),
            "destination_account": account("98765432100"),
            "source": {"device_id": "synthetic-personal-device", "channel": "app", "ip": "198.51.100.23"},
        }
    )


def run():
    registry = synthetic_registry()
    clean = EntityRegistry(version="synthetic-empty")
    former = synthetic_registry()
    former = former.model_copy(
        update={
            "links": tuple(
                link.model_copy(update={"valid_until": AT - timedelta(days=3)}) for link in former.links
            )
        }
    )
    late = registry.model_copy(
        update={
            "links": tuple(
                link.model_copy(update={"valid_from": AT - timedelta(days=1)}) for link in registry.links
            )
        }
    )
    revoked = registry.model_copy(
        update={
            "incidents": tuple(event.model_copy(update={"revoked_at": AT}) for event in registry.incidents)
        }
    )
    future = registry.model_copy(
        update={
            "incidents": tuple(
                event.model_copy(update={"known_at": AT + timedelta(days=1)}) for event in registry.incidents
            )
        }
    )
    newcomer = "20000000000199"
    newcomer_registry = registry.model_copy(
        update={
            "links": (
                *registry.links,
                CorporateLink(
                    link_id="new-company-control",
                    person_or_company=PERSON,
                    company=newcomer,
                    role="controller",
                    verified=True,
                    valid_from=AT - timedelta(days=1),
                    known_at=AT - timedelta(days=1),
                    reference="SYNTHETIC-new-company",
                ),
            )
        }
    )
    own = [
        OwnEvidence("own-a", PERSON, AT - timedelta(hours=2), 20, "account-a"),
        OwnEvidence("own-b", PERSON, AT - timedelta(hours=1), 20, "account-b"),
    ]
    cases = [
        ("clean_cpf_ten_confirmed_companies", PERSON, registry, [], "two_factor_required"),
        ("new_cnpj_same_controller", newcomer, newcomer_registry, [], "two_factor_required"),
        ("accountant_ten_companies", PERSON, synthetic_registry(role="accountant"), [], "approved"),
        ("minority_ten_companies", PERSON, synthetic_registry(role="minority_partner"), [], "approved"),
        ("administrator_ten_companies", PERSON, synthetic_registry(role="administrator"), [], "approved"),
        ("same_incident_ten_companies", PERSON, synthetic_registry(shared_incident=True), [], "approved"),
        ("former_controller", PERSON, former, [], "approved"),
        ("joined_after_fraud", PERSON, late, [], "approved"),
        ("revoked_incidents", PERSON, revoked, [], "approved"),
        ("future_discovered_fraud", PERSON, future, [], "approved"),
        ("new_account_same_cpf_own_history", PERSON, clean, own, "two_factor_required"),
        (
            "expired_own_history",
            PERSON,
            clean,
            [OwnEvidence("expired", PERSON, AT - timedelta(hours=25), 25)],
            "approved",
        ),
        ("missing_registry", PERSON, None, [], "approved"),
        (
            "fifty_clean_companies_do_not_dilute_one_risk",
            PERSON,
            synthetic_registry(51).model_copy(update={"incidents": (registry.incidents[0],)}),
            [],
            "approved",
        ),
    ]
    status, metadata = DecisionEngine(Policy()).evaluate(
        normal_candidate(), History(0, 0, 3, True, True, 3, 30_000)
    )
    results = []
    for name, doc, data, evidence, expected in cases:
        service = EntityRiskService("contribute", registry=data)
        assessment = service.assess(doc, AT, evidence)
        final, enriched = combine_entity_risk(status, metadata, assessment)
        shadow = EntityRiskService("shadow", registry=data).assess(doc, AT, evidence)
        shadow_status, shadow_metadata = combine_entity_risk(status, metadata, shadow)
        assert (
            final == expected
            and shadow_status == status
            and shadow_metadata["risk_score"] == metadata["risk_score"]
        ), (name, final, expected, assessment)
        results.append(
            {
                "scenario": name,
                "baseline_status": status,
                "contribute_status": final,
                "baseline_score": metadata["risk_score"],
                "score": enriched["risk_score"],
                "own_entity_untrust": assessment["own_entity"]["score"],
                "related_exposure": assessment["relationships"]["exposure_score"],
                "independent_incidents": assessment["relationships"]["confirmed_incidents"],
                "proposed_action": assessment["proposed_action"],
                "shadow_preserved": True,
            }
        )
    # The max records direct risk even among nine clean destinations. It does not
    # declare fraud or add points from unsettled attempts.
    payments = [
        PaymentEvidence(
            f"payment-{i}",
            PERSON,
            str(i),
            10_000,
            AT - timedelta(minutes=i + 1),
            AT - timedelta(minutes=i + 1),
            "approved",
        )
        for i in range(10)
    ]
    directed = financial_features(PERSON, AT, payments, {str(i): 90 if i == 0 else 0 for i in range(10)})
    return registry, {
        "scope": "SYNTHETIC behavioral contract comparison; not fraud precision/recall or real-world validation",
        "cases": len(results),
        "all_expected_behaviors_verified": True,
        "results": results,
        "financial_max_vs_mean_example": {"previous_mean_if_used": 9, "new_features": directed},
        "limits": [
            "Trusted operator registry, no Receita/DICT integration",
            "Relationship action requests 2FA; bounded graph points still follow the existing score rejection policy",
            "Financial features are observational because settlement is unknown",
            "Default API mode is shadow; contribute behavior shown explicitly",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/entity-risk-comparison.metrics.json"))
    parser.add_argument("--registry-output", type=Path, default=Path("examples/entity-registry.example.json"))
    args = parser.parse_args()
    registry, report = run()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.registry_output.write_text(registry.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
