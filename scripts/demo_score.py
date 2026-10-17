"""Demonstrate three score outcomes over HTTP with new synthetic payers and IDs."""

import argparse
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--save-response", type=Path, help="Save the complete rejected response as JSON")
    args = parser.parse_args()
    token = os.environ.get("INTERNAL_TOKEN", "default_token")
    template = json.loads((Path(__file__).resolve().parents[1] / "examples/pix.json").read_text())
    at = datetime.now(timezone.utc)

    def payload():
        body = copy.deepcopy(template)
        body["source_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
        body["source_account"]["opening_date"] = (at - timedelta(days=365)).isoformat()
        body["destination_account"]["opening_date"] = (at - timedelta(days=365)).isoformat()
        body["transaction_date"] = at.isoformat()
        body["amount"] = 1000
        return body

    def post(body):
        body = copy.deepcopy(body)
        body["id"] = "demo-score-" + uuid4().hex
        request = Request(
            args.url.rstrip("/") + "/pix/transaction",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "INTERNAL-TOKEN": token},
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def seed(body, count):
        for i in range(count):
            candidate = copy.deepcopy(body)
            candidate["amount"] = 10_000
            candidate["transaction_date"] = (at - timedelta(hours=i + 1)).isoformat()
            if post(candidate)["status"] != "approved":
                raise RuntimeError("Synthetic profile seed was not approved")

    normal = post(payload())
    uncertain = payload()
    seed(uncertain, 3)
    uncertain["amount"] = 50_000
    uncertain["source"]["device_id"] = "unfamiliar-device"
    uncertain["destination_account"]["account_number"] = "unfamiliar-destination"
    challenged = post(uncertain)
    risky = payload()
    seed(risky, 5)
    risky["amount"] = 100_000
    risky["destination_account"]["account_number"] = "unfamiliar-destination"
    risky["destination_account"]["opening_date"] = at.isoformat()
    rejected = post(risky)
    for label, response, expected_status, expected_score in (
        ("normal", normal, "approved", 0),
        ("combined_signals", challenged, "two_factor_required", 35),
        ("high_risk", rejected, "rejected", 80),
    ):
        if (response["status"], response["metadata"].get("risk_score")) != (expected_status, expected_score):
            raise RuntimeError(f"Unexpected decision for {label}: {response}")
        print(
            json.dumps(
                {
                    "scenario": label,
                    "status": response["status"],
                    "risk_score": response["metadata"]["risk_score"],
                    "reasons": response["metadata"]["reasons"],
                }
            )
        )
    if args.save_response:
        args.save_response.write_text(json.dumps(rejected, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
