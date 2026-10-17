"""Create isolated synthetic graph histories and inspect the experimental API output."""

import argparse
import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4

from src.gnn.synthetic import scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--require-contribution",
        action="store_true",
        help="Fail unless at least one real GNN inference increases the final score",
    )
    args = parser.parse_args()

    def post(body):
        request = Request(
            args.url.rstrip("/") + "/pix/transaction",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "INTERNAL-TOKEN": os.environ.get("INTERNAL_TOKEN", "default_token"),
            },
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    applied = False
    for kind in ("normal", "merchant", "ring"):
        candidate, history, label, _ = scenario(uuid4().int % 10_000_000, "demo", kind)
        for record in history:
            post(record)
        response = post(candidate)
        metadata = response["metadata"]
        applied = applied or metadata.get("gnn", {}).get("applied_points", 0) > 0
        if metadata.get("gnn", {}).get("status") != "scored":
            raise RuntimeError(f"GNN could not score scenario {kind}: {metadata.get('gnn')}")
        print(
            json.dumps(
                {
                    "synthetic_scenario": kind,
                    "synthetic_label": label,
                    "status": response["status"],
                    "risk_score": metadata["risk_score"],
                    "gnn": metadata["gnn"],
                }
            )
        )

    if args.require_contribution and not applied:
        raise RuntimeError("No GNN contribution was applied; run this demo against GNN_MODE=contribute")


if __name__ == "__main__":
    main()
