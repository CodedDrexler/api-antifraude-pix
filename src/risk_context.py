"""Shared, explicit reference for contextual night scoring, independent of host timezone."""

from datetime import timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3), "UTC-03:00")

FACTOR_LABELS = {
    "duplication": "Possível Pix duplicado",
    "exposure": "Histórico inicial",
    "activity": "Volume e frequência",
    "account": "Idade da conta de origem",
    "counterparty": "Destinatário",
    "profile": "Perfil de valores",
    "device": "Vínculos de dispositivos",
    "access_context": "Canal e horário",
    "graph": "Padrão relacional (GNN experimental)",
}


def is_night(at, policy):
    hour = at.astimezone(BRASILIA).hour
    return hour >= policy.night_start_hour or hour < policy.night_end_hour
