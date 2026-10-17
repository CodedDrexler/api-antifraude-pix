FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY models ./models

FROM base AS gnn-training
COPY requirements-gnn.txt .
RUN pip install --no-cache-dir -r requirements-gnn.txt
COPY scripts ./scripts
CMD ["python", "-m", "scripts.train_gnn", "--output", "/app/models/gnn-synthetic-v1.json"]

FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY scripts ./scripts
COPY examples ./examples
COPY pyproject.toml .
CMD ["pytest", "-v"]

FROM base AS api
RUN useradd --create-home api
USER api

EXPOSE 8000

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
