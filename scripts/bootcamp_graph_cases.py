"""Contract examples plus explicit fictitious histories, evaluated at frozen thresholds."""

import argparse
import copy
import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine

from scripts.validate_temporal_gnn import ROOT, SEEDS, evaluate_case, proposed_status
from src.constants import Policy
from src.gnn.temporal_service import TemporalGraphService


def cases():
    example = json.loads((ROOT / "examples/pix.json").read_text(encoding="utf-8"))
    yield "original_first_pix", example, [], None
    base = copy.deepcopy(example)
    # Incoming destination accounts require an institution. Make the payer's
    # identity explicit so incoming/outgoing events refer to the same account.
    base["source_account"]["participant"] = "60701190"
    at = datetime.fromisoformat(base["transaction_date"])

    def payment(name, hours, amount, source=None, destination=None):
        result = copy.deepcopy(base)
        result.update(
            id="bootcamp-validation-" + name,
            amount=amount,
            transaction_date=(at - timedelta(hours=hours)).isoformat(),
        )
        if source is not None:
            result["source_account"] = copy.deepcopy(source)
            result["source"]["device_id"] = "device-" + source["owner"]["document_number"]
        if destination is not None:
            result["destination_account"] = copy.deepcopy(destination)
        return result

    familiar = [
        payment("profile-1", 72, 49_999),
        payment("profile-2", 48, 150_000),
        payment("profile-3", 24, 150_000),
    ]
    yield "habitual_payment", copy.deepcopy(base), copy.deepcopy(familiar), 0
    unknown = copy.deepcopy(base)
    unknown["destination_account"]["account_number"] += "-new"
    yield "new_recipient_without_other_risk", unknown, copy.deepcopy(familiar), 0

    senders = []
    for index in range(2):
        sender = copy.deepcopy(base["destination_account"])
        sender.update(account_number=f"sender-{index}", opening_date=base["source_account"]["opening_date"])
        sender["owner"]["document_number"] = f"{11122233340 + index:011d}"
        senders.append(sender)
    flows = []
    for index, sender in enumerate(senders):
        received_hours = 2 - index
        flows.append(payment(f"receipt-{index}", received_hours, 100_000, sender, base["source_account"]))
        flows.append(payment(f"settlement-{index}", received_hours - 5 / 60, 95_000))
    yield "legitimate_fast_settlement", copy.deepcopy(base), copy.deepcopy(familiar + flows), 0

    own_risk = []
    for index, sender in enumerate(senders):
        own_risk.append(payment(f"sender-{index}-reference", 30, 1000, sender))
        for attempt in range(4):
            own_risk.append(payment(f"sender-{index}-risk-{attempt}", 20 - attempt, 100_000, sender))
    yield (
        "synthetic_mule_with_risky_senders",
        copy.deepcopy(base),
        copy.deepcopy(familiar + own_risk + flows),
        1,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold-report", type=Path, default=ROOT / "models/gnn-v9-validation.metrics.json"
    )
    parser.add_argument("--output", type=Path, default=Path("models/gnn-v9-bootcamp.metrics.json"))
    args = parser.parse_args()
    url = os.environ.get("PIX_TEST_DATABASE_URL")
    if not url:
        parser.error("Use PIX_TEST_DATABASE_URL for a dedicated verification database")
    thresholds = json.loads(args.threshold_report.read_text(encoding="utf-8"))
    policy = Policy.from_file(str(ROOT / "config/risk-policy.json"))
    if thresholds["policy"] != asdict(policy):
        raise ValueError("Threshold report must match the evaluated policy")
    services = {
        seed: TemporalGraphService(model_path=ROOT / f"models/gnn-directed-temporal-v2-seed-{seed}.json")
        for seed in SEEDS
    }
    if not all(service.enabled for service in services.values()):
        raise RuntimeError("Every frozen model must load successfully")
    if any(run["model_sha256"] != services[run["seed"]].model.sha256 for run in thresholds["runs"]):
        raise ValueError("Frozen thresholds must belong to the same model artifacts")
    results = []
    engine = create_engine(url)
    try:
        for name, candidate, records, label in cases():
            result = evaluate_case(engine, services, policy, candidate, records, label, name)
            result["proposals_at_previously_frozen_thresholds"] = {
                f"{run['seed']}/{run['method']}": proposed_status(
                    result, run["seed"], run["method"], run["calibration"]["threshold"]
                )
                for run in thresholds["runs"]
            }
            results.append(result)
    finally:
        engine.dispose()
    report = {
        "scope": "Examples from examples/pix.json with explicit fictitious histories; illustrative contract checks, not a population accuracy estimate",
        "thresholds_reused_without_tuning": str(args.threshold_report.name),
        "examples_sha256": hashlib.sha256((ROOT / "examples/pix.json").read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
