"""Export the v2 graph and decision for the fast/slow temporal regression case.

All data are synthetic. No HTTP, database writes, training or policy changes.
The offline fixture simulates receipt time with the event clock.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from scripts.evaluate_graph_untrust import replay
from scripts.temporal_graph_examples import source_scenario
from src.constants import Policy
from src.gnn.common import account_identity
from src.gnn.temporal_graph import RELATIONS, GraphEvent, build_temporal_graph
from src.gnn.temporal_service import ORIGINAL_TEMPORAL_MODEL, TemporalGraphService, TemporalHistory


def reproduce():
    service = TemporalGraphService(model_path=ORIGINAL_TEMPORAL_MODEL)
    assert service.enabled, "The versioned seed-42 model must be available"
    result = {
        "scope": "SYNTHETIC OFFLINE REPRODUCTION, NOT CONFIRMED FRAUD",
        "policy": Policy().version,
        "seed": 500_001,
        "test": "tests/test_temporal_gnn.py::test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction",
        "integration_test": "tests/test_temporal_case.py::test_v2_case_runs_through_database_decision_and_replay",
        "model_version": service.model.version,
        "model_sha256": service.model.sha256,
        "receipt_clock": "simulated_equal_to_event_time",
        "cases": [],
    }
    for kind in ("temporal_fast", "temporal_slow"):
        candidate, records, _, _ = source_scenario(result["seed"], "test", kind)
        tx, past, rule_status, final_status, metadata = replay(candidate, records, Policy())
        events = [
            GraphEvent(r.tx.model_dump(mode="json"), r.tx.transaction_date, r.status, r.increment)
            for r in past
        ]
        graph = build_temporal_graph(candidate, events)
        observed = service.assess(candidate, tx.transaction_date, TemporalHistory(events, events))
        source_key = account_identity(candidate["source_account"])
        flow = []
        for row in past:
            is_in = account_identity(row.tx.destination_account.model_dump()) == source_key
            is_out = account_identity(row.tx.source_account.model_dump()) == source_key
            age = (tx.transaction_date - row.tx.transaction_date).total_seconds() / 3600
            if (is_in or is_out) and age < 24 and row.status != "rejected":
                flow.append(
                    {
                        "id": row.tx.id,
                        "direction": "incoming" if is_in else "outgoing",
                        "amount_cents": row.tx.amount,
                        "event_time": row.tx.transaction_date.isoformat(),
                        "sender": row.tx.source_account.owner.document_number,
                        "recipient": row.tx.destination_account.owner.document_number,
                    }
                )
        matches = {r["code"]: r for r in metadata["triggered_rules"]}
        case = {
            "kind": kind,
            "gap_minutes": 5 if kind == "temporal_fast" else 120,
            "candidate": candidate,
            "history_count": graph.history_count,
            "graph_nodes": [
                {"id": i, "kind": key[0], "key": list(key), "own_untrust": round(float(graph.x[i, 11]) * 100)}
                for i, key in enumerate(graph.node_keys)
            ],
            "graph_edges": [
                {"relation": name, "source": int(pair[0]), "target": int(pair[1]), "weight": float(weight)}
                for name, part, weights in zip(RELATIONS, graph.edges, graph.edge_weights, strict=True)
                for pair, weight in zip(part.T, weights, strict=True)
            ],
            "target_nodes": graph.targets.tolist(),
            "rapid_pairs": round(float(graph.transaction_features[8]) * 4),
            "v2_score": observed["gnn_score"],
            "rule_status": rule_status,
            "final_status": final_status,
            "risk_score": metadata["risk_score"],
            "triggered_rules": metadata["triggered_rules"],
            "rules_evaluated": [
                {
                    "code": code,
                    "triggered": code in matches,
                    "weight": weight,
                    "contribution": matches.get(code, {}).get("contribution", 0),
                }
                for code, weight in asdict(Policy().scoring.weights).items()
            ],
            "shadow": {
                key: observed[key] for key in ("mode", "status", "applied_points", "decision_override")
            },
            "normalized_transaction_features": observed["normalized_transaction_features"],
            "recent_flow": flow,
            "profile_count": metadata["profile_transactions"],
            "profile_average_cents": metadata["profile_average"],
            "known_device": metadata["known_device"],
            "known_destination": metadata["known_destination"],
        }
        assert observed["status"] == "scored"
        assert observed["applied_points"] == 0 and observed["decision_override"] is False
        assert len(case["rules_evaluated"]) == 13
        result["cases"].append(case)
    fast, slow = result["cases"]
    assert fast["rapid_pairs"] == 2 and slow["rapid_pairs"] == 0
    assert fast["v2_score"] > slow["v2_score"]
    assert fast["risk_score"] == slow["risk_score"] == 25
    result["assertions"] = {
        "all_13_rules_evaluated": True,
        "different_temporal_pattern": True,
        "v2_does_not_override_decision": True,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reproduce()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            [
                {key: c[key] for key in ("kind", "rapid_pairs", "v2_score", "risk_score", "final_status")}
                for c in result["cases"]
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
