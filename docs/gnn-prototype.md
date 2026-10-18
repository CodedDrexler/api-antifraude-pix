# Experimental GNN

Experimento posterior, separado do modelo da API:
[grafo v2 com direção, titularidade e tempo](graph-v2-experiment.md).
Compara o v1 retreinado, um modelo tabular e o v2 em três sementes, incluindo
casos parecidos com intenções diferentes. O restante deste documento descreve
o protótipo v1 e suas métricas originais.

Desde 18/10/2026, o v2 também [roda na API em shadow](graph-v2-api.md),
com evidências próprias em `gnn_v2`. O v1 continua com seu modo independente.

## Resumo em português

O modelo é um **GraphSAGE supervisionado de duas camadas**, com agregação média
dos vizinhos. Contas e dispositivos são nós; transferências e uso de aparelhos
criam arestas bidirecionais. Cada camada combina o estado do nó com a média dos
vizinhos. O classificador final combina as representações da origem, do destino
e do aparelho com valor, idade das contas e frequência do pagador.

O treino usa cenários sintéticos com rótulos do gerador, sem copiar decisões das
regras. Inclui famílias compartilhando aparelhos e comerciantes legítimos, além
de redes de compartilhamento e concentração em destinatários. Não usa IP,
geolocalização, canal ou horário como variáveis do modelo atual. As regras
explícitas de canal/horário e diversidade de titulares complementam o GNN.
Nos atributos do grafo, "users" de um aparelho significa contas de origem distintas;
a nova regra `shared_device` distingue titulares pelo documento. São medidas diferentes.

O padrão **shadow** apenas observa. Dados insuficientes, vizinhança truncada e
falhas provocam abstenção explícita. O modo optativo **contribute** aplica até
20 pontos. Nenhuma métrica sintética comprova a eficácia no tráfego real.
Os pesos e o formato de atributos do modelo existente foram preservados;
alterar esses atributos exige retreino e avaliação temporal.

Available on `main`, originally developed on `codex/gnn-prototype`. This is a
synthetic-data demonstration, not a model validated against real fraud.
Rules remain the decision baseline; the GNN defaults to shadow mode.

## What was implemented

A supervised, two-layer mean GraphSAGE network learns account/device embeddings
from synthetic transaction graphs. A learned transaction classifier combines the
sender, recipient and device embeddings with candidate transaction features.
Weights are optimized with PyTorch, binary cross-entropy and Adam; they are not
hand-written point rules. The API runs the exported network in NumPy to avoid a
PyTorch dependency in the request-serving container.

This follows the neighborhood aggregation idea in the [GraphSAGE paper](https://arxiv.org/abs/1706.02216).
[PyTorch Geometric's heterogeneous graph documentation](https://pytorch-geometric.readthedocs.io/en/latest/notes/heterogeneous.html)
describes typed entities and relations. This implementation uses account/device
type features with a shared GraphSAGE operator, rather than PyG or separate
relation-specific operators. It uses neither an external inference API nor a graph database.

## Point-in-time features

Account nodes use type, incoming/outgoing attempt counts, distinct counterparties,
mean attempted amounts and supplied account age. Device nodes use type and
distinct historical users. Relations link sender to receiver and sender to device;
both directions are available to message passing. Candidate features contain
amount, account ages and payer frequency. Node IDs, generator scenario, fraud
labels, rule decisions and rule scores never enter the model features.

History is limited to 30 days and 300 earlier attempts related to the current
payer, receiver or device. Events with future event timestamps are excluded.
Equal event timestamps can include previously received attempts. The candidate's
relations are known at request time, but its amount is not added to history.
Duplicate IDs are removed. The graph is one bounded neighborhood, not a complete
network or an investigation of arbitrary paths through the database.

At least 3 historical attempts are required. If there are more than 300 matching
attempts, the GNN abstains with `history_truncated`, instead of silently scoring
an incomplete graph. Missing/invalid models and inference failures return an
explicit unavailable status and zero contribution. PostgreSQL errors still use
the API's existing 503 behavior. No model is trained during a request.

The model is loaded once at application creation. Only JSON weights with expected
shapes and finite numbers are accepted; no pickle or executable model artifact
is loaded. The model SHA-256 is recorded in each saved analysis.

## Modes and risk contribution

| GNN_MODE | Behavior |
|---|---|
| off | Rule scoring only; model is not loaded and graph history is not queried |
| shadow (default) | Saves GNN assessment alongside the rule decision; final risk is unchanged |
| contribute | Experimental opt-in: a GNN score >= 80 adds 20 graph points, capped by total score 100 |

The default response shows only GNN mode, status, score and applied points.
Use `?include_details=true` on POST or GET for the saved audit fields below.
In that detailed view, `metadata.rule_risk_score` records the baseline. `metadata.gnn.gnn_score` is the
network sigmoid output multiplied by 100. It is **uncalibrated** and must not be
read as a probability of fraud. `proposed_points` is the graph group contribution;
`applied_points` is the actual change in the final score after the global cap.
The original hard limits always win. Graph points cannot reduce risk or override
a hard rejection. The graph group may correlate with existing rules; its 20-point
cap limits impact but does not eliminate double counting or validate calibration.

Contribute mode can change approval/2FA/rejection outcomes when explicitly enabled.
It records policy version `pix-score-v6+gnn-experimental-v1`. Shadow preserves the
rule policy version and result, while also recording graph configuration and model hash.
Saved decisions remain immutable and retries never re-evaluate a model or mode.

## Run and demonstrate

The trained JSON weights and metrics are included. No training download is needed
to start the API or run tests. From a new checkout:

```powershell
docker compose up --build --wait api
docker compose --profile test build tests
docker compose --profile test run --rm --no-deps tests
docker compose --profile test run --rm --no-deps tests python -m scripts.demo_gnn --url http://api:8000
```

The demonstration creates new, synthetic identities and inserts their histories.
It shows a normal payer, a legitimate merchant and a ring. It adds test data
without deleting existing history. Model scores can vary with the generated graph.

To test actual risk contribution, set `GNN_MODE=contribute` in `.env` or the shell,
then recreate the API. In PowerShell:

```powershell
$env:GNN_MODE = 'contribute'
docker compose up -d --wait api
docker compose --profile test run --rm --no-deps tests python -m scripts.demo_gnn --url http://api:8000
```

The full contract suite expects default shadow mode. Restore `GNN_MODE=shadow`
before running it. Use new transaction IDs when comparing modes. For an existing
database, apply the additive indexes once; do not remove its volume:

```powershell
Get-Content -Raw database/migrations/002_gnn_graph_indexes.sql | docker compose exec -T db psql -U pix -d pix -v ON_ERROR_STOP=1
```

## Train and evaluate again

```powershell
docker compose --profile gnn build gnn-training
docker compose --profile gnn run --rm gnn-training
docker compose up --build --wait api
```

Training is CPU-only, deterministic within the pinned image/seed, and optional.
It uses 500 training graphs, 150 validation graphs and 200 held-out test graphs.
The three splits have separate identities and January/May/September timestamps;
every example's history precedes its candidate. Best epoch and classification
threshold are selected using validation data, not test labels.

Synthetic scenarios: ordinary payments, merchants, families sharing a device,
device-sharing rings, receiver fan-in and legitimate new merchants that resemble
fan-in attacks. Labels come from generator intent, never from the rule engine.
This small generator has strong assumptions and does not represent Pix traffic.

Recorded results, seed 42:

| Held-out synthetic test (200 graphs) | Result |
|---|---|
| ROC-AUC | 0.963 |
| Validation-selected threshold | 0.50 |
| Precision / recall at 0.50 | 0.754 / 0.860 |
| False positives / missed fraud at 0.50 | 16 / 8 |
| Runtime contribution threshold | 0.80 |
| Precision / recall at 0.80 | 1.000 / 0.632 |
| False positives / missed fraud at 0.80 | 0 / 21 |
| Maximum PyTorch vs NumPy output error | < 0.000001 |

The runtime threshold was chosen conservatively for the prototype, independently
of the validation-selected F1 threshold; both are reported. Zero false positives
in 143 synthetic legitimate examples provides no guarantee outside this generator.
The report also removes message-passing edges at evaluation as a topology ablation.
That is an ablation of the trained model, not a separately trained tabular baseline.
Inference timing in the report measures only NumPy prediction, excluding graph
construction, database access, queueing and HTTP latency.

Full artifact and metrics: `models/gnn-synthetic-v1.json` and
`models/gnn-synthetic-v1.metrics.json`. Changing training data or schema requires
retraining, evaluation and a new model version before comparisons are meaningful.
Real use would require confirmed outcomes, representative temporal holdouts,
calibration, monitoring, privacy controls and evaluation against simpler baselines.
