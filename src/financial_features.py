"""Directional, point-in-time financial features; attempts never prove settlement."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PaymentEvidence:
    event_id: str
    source_document: str
    destination_document: str
    amount: int
    transaction_at: datetime
    received_at: datetime
    status: str


def eligible_payments(document, at, payments):
    return sorted(
        {
            row.event_id: row
            for row in payments
            if row.status != "rejected"
            and row.source_document != row.destination_document
            and document in {row.source_document, row.destination_document}
            and at - timedelta(hours=24) < row.received_at <= at
            and at - timedelta(hours=24) < row.transaction_at <= at
        }.values(),
        key=lambda row: (row.transaction_at, row.event_id),
    )


def directional_contacts(document, at, payments):
    incoming, outgoing = {}, {}
    for row in eligible_payments(document, at, payments):
        if row.source_document == document:
            outgoing[row.destination_document] = row.transaction_at
        else:
            incoming[row.source_document] = row.transaction_at
    return {
        direction: [
            doc for doc, _ in sorted(contacts.items(), key=lambda pair: (-pair[1].timestamp(), pair[0]))[:10]
        ]
        for direction, contacts in (("incoming", incoming), ("outgoing", outgoing))
    }


def financial_features(document, at, payments, untrust_by_document, *, truncated=False):
    result = {
        "status": "history_truncated" if truncated else "assessed",
        "data_basis": "non_rejected_attempts_not_confirmed_settlement",
        "score_contribution": 0,
        "window_hours": 24,
        "contacts_per_direction": 10,
    }
    if truncated:
        return result
    rows = eligible_payments(document, at, payments)
    contacts = directional_contacts(document, at, payments)
    for direction, documents in contacts.items():
        scores = [untrust_by_document[doc] for doc in documents if doc in untrust_by_document]
        result[direction] = {
            "contacts": len(documents),
            "unknown_untrust_contacts": len(documents) - len(scores),
            "max_untrust": max(scores) if scores else None,
            "top_untrust": sorted(scores, reverse=True)[:3],
            "suspect_fraction": sum(score >= 40 for score in scores) / len(documents) if documents else 0,
        }
    available, repasses = [], 0
    for row in rows:
        if row.destination_document == document:
            available.append(row)
            continue
        matches = [
            entry
            for entry in available
            if timedelta(0) < row.transaction_at - entry.transaction_at <= timedelta(minutes=30)
            and 0.8 * entry.amount <= row.amount <= entry.amount / 0.8
            and entry.source_document != row.destination_document
        ]
        if matches:
            available.remove(max(matches, key=lambda entry: entry.transaction_at))
            repasses += 1
    result["rapid_repass_pairs"] = repasses
    result["repass_with_suspect_destination"] = (
        repasses >= 2 and (result["outgoing"]["max_untrust"] or 0) >= 40
    )
    return result
