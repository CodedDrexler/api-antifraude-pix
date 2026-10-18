"""Public names for applied rules; stored evidence keeps its stable rule codes."""

RULE_ALIASES = {
    "velocity_above_limit": "Muitas transações em pouco tempo",
    "accumulated_amount_above_limit": "Valor acumulado acima do limite",
    "first_transaction": "Primeira transação",
    "insufficient_amount_history": "Histórico de valores insuficiente",
    "amount_requires_two_factor": "Valor exige autenticação adicional",
    "new_source_account": "Conta de origem recente",
    "new_destination_account": "Conta de destino recente",
    "unfamiliar_destination": "Destinatário desconhecido",
    "amount_above_customer_profile": "Valor acima do perfil do cliente",
    "unfamiliar_device": "Dispositivo desconhecido",
    "shared_device": "Dispositivo compartilhado entre titulares",
    "multiple_devices": "Uso de vários dispositivos",
    "unusual_night_app": "Uso noturno fora do habitual",
    "possible_duplicate_payment": "Possível pagamento duplicado",
    "account_untrust": "Desconfiança acumulada da conta",
    "gnn_relational_pattern": "Padrão de risco nas relações entre contas",
    "verified_entity_relationship_exposure": "Risco em vínculos verificados do titular",
    "own_entity_untrust": "Desconfiança acumulada do titular",
    "own_entity_confirmed_incident": "Incidente confirmado envolvendo o titular",
    "verified_control_multiple_incidents": "Vínculos verificados com múltiplos incidentes",
}


def rule_alias(code: str) -> str:
    return RULE_ALIASES.get(code, code.replace("_", " ").capitalize())
