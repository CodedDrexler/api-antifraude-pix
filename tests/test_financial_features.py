from datetime import datetime, timedelta, timezone

from src.financial_features import PaymentEvidence, financial_features

NOW = datetime(2026, 10, 17, 15, tzinfo=timezone.utc)


def payment(identifier, source, destination, minutes, *, status="approved", amount=10_000):
    return PaymentEvidence(
        identifier,
        source,
        destination,
        amount,
        NOW - timedelta(minutes=minutes),
        NOW - timedelta(minutes=minutes),
        status,
    )


def test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted():
    rows = [payment("suspicious-receipt", "bad", "payer", 60)]
    rows += [payment(f"clean-{i}", "payer", f"clean-{i}", 40 - i) for i in range(9)]
    scores = {"bad": 90, **{f"clean-{i}": 0 for i in range(9)}}
    result = financial_features("payer", NOW, rows, scores)
    assert result["incoming"]["max_untrust"] == 90
    assert result["outgoing"]["max_untrust"] == 0
    rows.append(payment("suspicious-destination", "payer", "bad", 5))
    result = financial_features("payer", NOW, rows, scores)
    assert result["outgoing"]["max_untrust"] == 90
    assert result["outgoing"]["suspect_fraction"] == 0.1
    assert result["score_contribution"] == 0


def test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy():
    rows = [
        payment("in1", "a", "payer", 60, status="two_factor_required"),
        payment("out1", "payer", "bad", 55),
        payment("duplicate-out", "payer", "bad", 50),
        payment("in2", "b", "payer", 40),
        payment("out2", "payer", "bad", 35),
    ]
    result = financial_features("payer", NOW, rows + rows, {"bad": 90, "a": 0, "b": 0})
    assert result["rapid_repass_pairs"] == 2
    assert result["repass_with_suspect_destination"]
    assert result["score_contribution"] == 0
    assert result["data_basis"] == "non_rejected_attempts_not_confirmed_settlement"


def test_future_old_rejected_and_self_transfers_do_not_create_exposure():
    rows = [
        payment("future", "payer", "bad", -1),
        payment("old", "payer", "bad", 1500),
        payment("rejected", "payer", "bad", 30, status="rejected"),
        payment("self", "payer", "payer", 20),
    ]
    result = financial_features("payer", NOW, rows, {"bad": 90})
    assert result["outgoing"]["contacts"] == result["incoming"]["contacts"] == 0
    assert result["rapid_repass_pairs"] == 0


def test_truncation_and_unknown_counterparty_risk_are_explicit():
    rows = [payment("unknown", "payer", "unknown", 30)]
    result = financial_features("payer", NOW, rows, {})
    assert result["outgoing"]["unknown_untrust_contacts"] == 1
    assert result["outgoing"]["max_untrust"] is None
    result = financial_features("payer", NOW, rows, {}, truncated=True)
    assert result["status"] == "history_truncated" and "outgoing" not in result
