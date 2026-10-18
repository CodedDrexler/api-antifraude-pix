"""Demonstrate account escalation and a metadata-only bank notification."""

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--save-response", type=Path)
    args = parser.parse_args()
    payload = json.loads((Path(__file__).resolve().parents[1] / "examples/pix.json").read_text())
    at = datetime.now(timezone.utc).replace(hour=15, minute=0, second=0, microsecond=0)
    payload["source_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    for account in (payload["source_account"], payload["destination_account"]):
        account["opening_date"] = (at - timedelta(days=365)).isoformat()
    payload["source"]["device_id"] = "untrust-device-" + uuid4().hex
    payload["destination_account"]["account_number"] = "destination-" + uuid4().hex

    def post(amount, date):
        body = deepcopy(payload)
        body.update(id="demo-untrust-" + uuid4().hex, amount=amount, transaction_date=date.isoformat())
        req = Request(
            args.url.rstrip("/") + "/pix/transaction",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    post(1000, at - timedelta(hours=2))
    assert post(1000, at - timedelta(hours=1))["status"] == "approved"
    for expected in (20, 40, 60, 80):
        result = post(5000, at)
        assert result["metadata"]["account_untrust"]["score"] == expected
        print(
            json.dumps({"step": "risk_attempt", "status": result["status"], "metadata": result["metadata"]})
        )
    result = post(1000, at)
    assert result["status"] == "two_factor_required"
    assert result["metadata"]["risk_score"] == 0
    assert result["metadata"]["account_untrust"]["score"] == 80
    assert result["metadata"]["bank_notification"]["status"] == "indicated_only"
    print(json.dumps({"step": "normal_next_pix", **result}))
    if args.save_response:
        args.save_response.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
