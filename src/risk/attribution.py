"""Risk subjects follow evidence semantics, independently of configurable scoring groups."""

RULE_SUBJECTS = {
    "velocity_above_limit": "sender",
    "accumulated_amount_above_limit": "sender",
    "first_transaction": "sender",
    "new_source_account": "sender",
    "new_destination_account": "destination",
    "unfamiliar_destination": "relationship",
    "amount_above_customer_profile": "transaction",
    "unfamiliar_device": "sender",
    "shared_device": "sender",
    "multiple_devices": "sender",
    "unusual_night_app": "transaction",
    "insufficient_amount_history": "sender",
    "possible_duplicate_payment": "transaction",
    "gnn_relational_pattern": "relationship",
    "verified_entity_relationship_exposure": "relationship",
}


def decision_causes(metadata, status, source=None):
    """Record the evidence used by the selected intervention, not a permanent fraud label."""
    if status == "approved":
        return []
    source = source or metadata["decision_source"]
    if source == "account_untrust":
        return [{"rule_id": source, "subject": "sender", "source": "local_history"}]
    if source == "entity_risk":
        return [
            {
                "rule_id": reason,
                "subject": "sender" if reason.startswith("own_entity_") else "relationship",
                "source": "local_history" if reason == "own_entity_untrust" else "operator_registry",
            }
            for reason in metadata.get("entity_risk", {}).get("reasons", [])
        ]
    rules = metadata.get("triggered_rules", [])
    if source == "hard_limit":
        rules = [rule for rule in rules if rule["hard_limit"]]
    elif source in {"first_transaction", "insufficient_history"}:
        code = "first_transaction" if source == "first_transaction" else "insufficient_amount_history"
        rules = [rule for rule in rules if rule["code"] == code]
    else:
        rules = [rule for rule in rules if rule["contribution"] > 0]
    return [
        {
            "rule_id": rule["code"],
            "subject": rule.get("subject", RULE_SUBJECTS.get(rule["code"], "transaction")),
            "source": rule.get("source", "local_history"),
            "contribution": rule["contribution"],
        }
        for rule in rules
    ]
