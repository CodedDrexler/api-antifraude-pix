"""Shared, explicit reference for contextual night scoring, independent of host timezone."""

from datetime import timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3), "UTC-03:00")

FACTOR_LABELS = {
    "duplication": "Possível repetição do mesmo pagamento",
    "exposure": "Histórico insuficiente para avaliar o Pix",
    "activity": "Quantidade e valor acumulado de Pix recentes",
    "account": "Tempo desde a abertura da conta de origem",
    "counterparty": "Conta de destino recente ou destinatário desconhecido",
    "profile": "Valor do Pix comparado aos pagamentos anteriores",
    "device": "Aparelho desconhecido, compartilhado ou trocado com frequência",
    "access_context": "Uso do aplicativo à noite fora do hábito do pagador",
    "graph": "Risco associado a vínculos societários verificados",
}


def is_night(at, policy):
    hour = at.astimezone(BRASILIA).hour
    return hour >= policy.night_start_hour or hour < policy.night_end_hour
