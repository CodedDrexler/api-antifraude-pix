# Pix Antifraude — Bootcamp QI Tech 2026

API em Python 3.12, FastAPI e PostgreSQL 16 com score explicável e histórico persistido.
Retorna `approved`, `two_factor_required` ou `rejected`. Política: `pix-score-v6`;
score heurístico de 0 a 100, sem representar probabilidade de fraude.

**Integrantes:** Vinícius Guimarães Drexler e Wallace Dametto Teixeira.

## Executar

Requer Docker Desktop com Docker Compose. Na raiz do projeto:

```powershell
docker compose up --build --wait
```

Abra o [Swagger](http://127.0.0.1:8000/docs), clique em **Authorize** e informe
`default_token`. Em **Analisar um Pix**, escolha um exemplo e use um ID novo;
o primeiro Pix exige 2FA. Aprovação depende de histórico compatível.

Porta, token e modo GNN são configuráveis em `.env`, conforme [.env.example](.env.example).
`docker compose down` encerra os serviços e preserva o histórico no volume `pix_data`.

## API

| Método e rota | Função |
|---|---|
| `POST /pix/transaction` | Analisa e grava pedido, decisão e evidências |
| `GET /pix/transaction/{id}` | Recupera a decisão original pelo ID enviado |
| `GET /health_check` ou `/health` | Verifica o processo |
| `GET /ready` | Verifica acesso à tabela no banco |

Rotas Pix exigem `INTERNAL-TOKEN`. A resposta contém `key`, `status` e `metadata`
com score, fatores, versão, origem e duração da análise. `?include_details=true`
inclui regras, histórico e política salvos. Exemplos: [pedido](examples/pix.json)
e [resposta](examples/scored-response.json).

- `amount`: inteiro em centavos (`150000` = R$ 1.500,00); datas ISO 8601 com fuso.
- `source.channel`: `app`, `internet_banking` ou outro canal informado pelo integrador.
- CPF/CNPJ aceita pontuação, com validação de formato; campos desconhecidos são recusados.
- Mesmo ID e conteúdo normalizado recuperam a decisão, sem reanálise; conteúdo diferente gera **409**.
- Erros: **400** entrada inválida, **403** token ausente/incorreto, **404** ID inexistente,
  **503** banco indisponível/timeout. Após 503, repita com o mesmo ID.

## Decisão

Histórico por documento do pagador, inclusive entre contas. Fatores: frequência,
montante, idade das contas, valores, destinatário, dispositivos, canal/horário e
duplicidade. Pontos têm teto por fator e total de 100.

| Condição padrão, em ordem de prioridade | Decisão |
|---|---|
| Sexta tentativa em 10 min ou montante na janela, incluindo o Pix atual, ≥ R$ 30 mil | `rejected` |
| Score ≥ 80 com pelo menos dois fatores positivos | `rejected` |
| Primeiro Pix, ausência de referência de valor ou score ≥ 30 | `two_factor_required` |
| Demais casos | `approved` |

- **Perfil:** ≥ 5 × a média de até 10 aprovações soma 80 pontos; sem aprovações,
  a primeira tentativa pendente de 2FA serve de referência provisória.
- **Duplicidade:** mesmas contas e valor, outro ID em até 120 s: +30 pontos e
  `duplicate_payment` com a tentativa anterior. Rejeições ficam fora.
- **Acumulado:** `account_untrust` usa 24 h pelo relógio do servidor, separado do score.
  ≥ 40 exige 2FA; ≥ 60 indica aviso sem envio. Rejeição por acumulado vem desativada.
- **GNN:** GraphSAGE sintético experimental. `GNN_MODE=shadow` apenas registra;
  `off` desliga; `contribute` permite até 20 pontos adicionais.

Configure regras, pesos e tetos em [risk-policy.json](config/risk-policy.json);
atualize `version` e rode `docker compose restart api`. Peso zero preserva limites
fortes e 2FA inicial. Decisões antigas mantêm suas evidências e política.

## Testar e desenvolver

**Windows:** com Docker Desktop aberto, dê dois cliques em [testar.bat](testar.bat)
ou rode `.\testar.bat --no-pause`: executa pytest, lint e formatação em ambiente
isolado e remove seus containers e banco temporário ao terminar.

**Compose:** com a API iniciada, use uma base de testes; são inseridos dados sintéticos.

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests ruff check src tests scripts
docker compose --profile test run --rm tests ruff format --check src tests scripts
docker compose --profile test run --rm tests python scripts/demo_score.py --url http://api:8000
```

A demonstração produz scores 0, 35 e 95.

**Sem Docker:** use Python 3.12 e PostgreSQL 16; instale `pip install -r requirements-dev.txt`,
inicialize o banco com [database.sql](database/database.sql), configure `DATABASE_URL`,
`INTERNAL_TOKEN` e `RISK_POLICY_PATH=config/risk-policy.json` e execute `python -m uvicorn src.app:app`.

**Bases existentes:** aplique as migrações necessárias à versão instalada:
[002 — índices GNN](database/migrations/002_gnn_graph_indexes.sql),
[004 — acumulado por conta](database/migrations/004_account_untrust.sql) e
[005 — índice de duplicidade](database/migrations/005_duplicate_payment.sql).
O SQL inicial só roda em banco novo. A [003 — permissões](database/migrations/003_runtime_role.sql)
requer revisão separada; não é pré-requisito da 004.

## Documentação e escopo

[Regras e evidências](docs/risk-scoring.md) · [Arquitetura](docs/architecture.md) ·
[Acumulado por conta](docs/account-untrust.md) · [GNN: treino e métricas](docs/gnn-prototype.md) ·
[Revisão bancária e pendências de produção](docs/banking-review.md).

Projeto demonstrativo: não executa 2FA, liquidação, envio de avisos ou gestão de limites
bancários. Aprovação local não confirma pagamento; o GNN não foi validado com fraude real.
