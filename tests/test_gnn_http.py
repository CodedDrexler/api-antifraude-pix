from copy import deepcopy
from uuid import uuid4

from conftest import request

from src.gnn.synthetic import scenario


def test_shadow_v2_assessment_is_saved_and_replayed(api):
    # Fresh synthetic identities prevent contamination by earlier runs.
    candidate, history, _, _ = scenario(uuid4().int % 10_000_000, "demo", "ring")
    for record in history:
        assert api("POST", "/pix/transaction", record)[0] == 200
    status, result, _ = api("POST", "/pix/transaction", candidate)
    assert status == 200
    m = result["metadata"]
    assert m["gnn_v2"]["mode"] == "contribute"
    assert m["gnn_v2"]["status"] == "scored"
    assert m["gnn_v2"]["training_data"] == "synthetic"
    assert m["gnn_v2"]["label"] == "Modelo Relacional Temporal v2 — experimental"
    assert 0 <= m["gnn_v2"]["gnn_score"] <= 100
    assert "gnn" not in m and "gnn" not in m["policy"]
    assert m["gnn_v2"]["applied_points"] == 0
    assert api("GET", "/pix/transaction/" + candidate["id"])[1] == result
    assert api("POST", "/pix/transaction", candidate)[1] == result
    public = request("POST", "/pix/transaction", candidate)[1]
    assert public["metadata"] == {
        "risk_score": m["risk_score"],
        "untrust_score": m["gnn_v2"]["gnn_score"],
        "bank_notification_required": m["bank_notification"]["required"],
    }
    assert request("GET", "/pix/transaction/" + candidate["id"])[1] == public
    detailed = request("GET", "/pix/transaction/" + candidate["id"], include_details=True)[1]
    assert set(detailed["metadata"]) == set(public["metadata"]) | {"rules"}
    assert all(isinstance(rule, str) and "_" not in rule for rule in detailed["metadata"]["rules"])


def test_future_cross_payer_history_cannot_influence_graph(api, payload):
    # Isolate the destination holder: v2 expands by document, not only account.
    payload["destination_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    future = deepcopy(payload)
    future["id"] = "future-" + uuid4().hex
    future["transaction_date"] = "2027-01-01T00:00:00Z"
    future["source_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    assert api("POST", "/pix/transaction", future)[0] == 200
    status, result, _ = api("POST", "/pix/transaction", payload)
    assert status == 200
    observed = result["metadata"]["gnn_v2"]
    assert observed["status"] == "insufficient_history"
    assert observed["history_transactions"] == 0
    assert observed["coverage"]["events"] == 0
