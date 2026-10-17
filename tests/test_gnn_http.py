from copy import deepcopy
from uuid import uuid4

from src.gnn.synthetic import scenario


def test_shadow_graph_assessment_is_saved_and_replayed(api):
    # Fresh synthetic identities prevent contamination by earlier runs.
    candidate, history, _, _ = scenario(uuid4().int % 10_000_000, "demo", "ring")
    for record in history:
        assert api("POST", "/pix/transaction", record)[0] == 200
    status, result, _ = api("POST", "/pix/transaction", candidate)
    assert status == 200
    m = result["metadata"]
    assert m["gnn"]["mode"] == "shadow"
    assert m["gnn"]["status"] == "scored"
    assert m["gnn"]["training_data"] == "synthetic"
    assert 0 <= m["gnn"]["gnn_score"] <= 100
    assert m["rule_risk_score"] == m["risk_score"]
    assert m["gnn"]["applied_points"] == 0
    assert api("GET", "/pix/transaction/" + candidate["id"])[1] == result
    assert api("POST", "/pix/transaction", candidate)[1] == result


def test_future_cross_payer_history_cannot_influence_graph(api, payload):
    future = deepcopy(payload)
    future["id"] = "future-" + uuid4().hex
    future["transaction_date"] = "2027-01-01T00:00:00Z"
    future["source_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    assert api("POST", "/pix/transaction", future)[0] == 200
    status, result, _ = api("POST", "/pix/transaction", payload)
    assert status == 200
    assert result["metadata"]["gnn"]["status"] == "insufficient_history"
