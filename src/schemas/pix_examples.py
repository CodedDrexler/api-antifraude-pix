"""Complete, fictitious Pix payloads for the interactive API documentation."""

from copy import deepcopy

PIX_REQUEST_EXAMPLE = {
    "id": "pix-000123",
    "amount": 150_000,
    "transaction_date": "2026-10-17T22:15:00-03:00",
    "source_account": {
        "branch": "0001",
        "account_number": "88213",
        "opening_date": "2025-03-02T10:00:00-03:00",
        "owner": {"document_number": "123.456.789-09"},
    },
    "destination_account": {
        "participant": "60701190",
        "branch": "3675",
        "account_number": "10442",
        "opening_date": "2026-10-10T09:00:00-03:00",
        "owner": {"document_number": "987.654.321-00"},
    },
    "source": {
        "device_id": "dvc-9f2c71a8",
        "channel": "app",
        "ip": "198.51.100.23",
        "geolocation": {"latitude": -23.56, "longitude": -46.65},
    },
}


def request_example(transaction_id, amount):
    example = deepcopy(PIX_REQUEST_EXAMPLE)
    example.update(id=transaction_id, amount=amount)
    return example


PIX_REQUEST_EXAMPLES = {
    "two_factor": {
        "summary": "Sem histórico: Pix de R$ 1.500,00 — solicita 2FA",
        "description": "Sem aprovações anteriores e com valor a partir de R$ 500, a política padrão exige 2FA. O valor de R$ 1.500 é ilustrativo.",
        "value": PIX_REQUEST_EXAMPLE,
    },
    "approved": {
        "summary": "Primeiro Pix de R$ 10,00 — pode aprovar",
        "description": "Abaixo de R$ 500, a ausência de histórico não exige 2FA. Aprova se as demais regras e o acumulado não exigirem intervenção.",
        "value": request_example("pix-000124", 1000),
    },
    "blocked": {
        "summary": "Pix de R$ 30.000,00 — bloqueado",
        "description": "Aciona o limite forte de montante acumulado na política padrão.",
        "value": request_example("pix-000125", 3_000_000),
    },
}
