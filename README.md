# Pix Antifraude — Bootcamp QI Tech 2026

**Integrantes:** Vinícius Guimarães Drexler, Wallace Dametto Teixeira

**Branch experimental `codex/gnn-prototype`:** inclui um GraphSAGE treinado com
dados sintéticos. O padrão `GNN_MODE=shadow` registra `metadata.gnn` sem alterar
a decisão por regras. `GNN_MODE=contribute` permite testar até 20 pontos adicionais.
Veja [implementação, métricas e comandos do GNN](docs/gnn-prototype.md).

API síncrona que recebe um Pix e responde `approved`, `rejected` ou
`two_factor_required`, com motivos explicáveis e histórico em PostgreSQL 16.
Baseada na organização do [repositório informado](https://github.com/CodedDrexler/bootcamp-qi-tech)
e no contrato do desafio do hackathon. Consulte [as decisões de arquitetura](docs/architecture.md)
para a relação com cada material, desenho de dados, concorrência e limites.

## Como o motor de decisão funciona

O resource recebe o JSON validado. O controller obtém o histórico do pagador,
executa a política e grava o pedido e a decisão na mesma transação do banco.
O motor não chama serviços externos. Cada análise preserva os sinais consultados,
todos os motivos acionados, o score de 0 a 100, a versão `pix-score-v2` e seus
parâmetros em `metadata`. O score é heurístico, sem interpretação de porcentagem
de fraude. A [pesquisa e a política de score](docs/risk-scoring.md) explicam as
fontes, os pesos e a calibração futura.

O documento normalizado do pagador agrupa o histórico, inclusive entre contas.
Velocity e montante usam a janela inclusiva de 10 minutos anterior à data do Pix,
contando **todas as tentativas válidas anteriores**, de qualquer decisão. O Pix
atual entra no cálculo de montante; o contador informa quantos pedidos já existiam.
Repetições do mesmo ID não entram de novo no histórico.

Perfil, destino conhecido e dispositivo conhecido usam somente análises aprovadas
nos últimos 30 dias, até a data do Pix. O destino é identificado por ISPB, agência,
conta e documento. Sem histórico suficiente, regras de perfil e dispositivo não
acionam; isso permite o primeiro uso sem presumir confiança já estabelecida.

## Regras

Os valores são hipóteses demonstrativas, sem calibração em uma base de fraudes
reais. Os limites fortes de valor, velocity e montante foram preservados.
As demais regras contribuem para o score e podem ser aprovadas isoladamente.
Condições, pesos e faixas ficam em `src/constants.py`: `Policy`, `ScoringPolicy`,
`RuleWeights` e `GroupCaps`.

| Regra | Lógica | Parâmetros | Por quê |
|---|---|---|---|
| Valor alto | +80; limite forte que reprova | R$ 20.000,00 | Limita exposição por tentativa; mantém o teto inicial |
| Velocity | +80; limite forte na sexta tentativa | 5 anteriores em 10 minutos | Detecta rajadas, mesmo quando reprovadas |
| Montante | +80; limite forte se soma + Pix atual atinge o teto | R$ 30.000,00 em 10 minutos | Detecta exposição acumulada abaixo do limite individual |
| Valor intermediário | +30 no grupo exposure | R$ 1.000,00 | Mantém confirmação para valores relevantes |
| Conta de origem nova | +15 no grupo account | Menos de 7 dias | Acrescenta risco sem desafiar isoladamente |
| Conta de destino nova | +15 no grupo counterparty se não houver aprovação para esse destino | Menos de 7 dias e Pix a partir de R$ 500,00 | Combina idade observada e exposição |
| Destino desconhecido | +15 no grupo counterparty | 3 aprovações anteriores; destino ausente; piso R$ 500,00 | Detecta novidade com uma amostra mínima |
| Desvio de perfil | +25 no grupo profile se valor atinge 5 vezes a média | 5 aprovações em 30 dias; piso R$ 500,00 | Detecta mudança de padrão sem amostra muito pequena |
| Dispositivo desconhecido | +20 no grupo device | 3 aprovações em 30 dias; dispositivo ausente; piso R$ 500,00 | Sinal de troca de aparelho, sem presumir fraude |

## Como as regras viram decisão

Todas as regras são avaliadas. A contribuição de cada grupo é limitada:
`exposure` 80, `activity` 80, `account` 15, `counterparty` 25, `profile` 25 e
`device` 20. Pesos maiores consomem o teto primeiro; empates seguem a ordem do
código da regra. A soma dos grupos é limitada a 100.

| Condição | Decisão |
|---|---|
| Qualquer limite forte | `rejected`, com `decision_source: hard_limit` |
| Score 0 a 29 | `approved` |
| Score 30 a 79 | `two_factor_required` |
| Score 80 a 100, com pelo menos 2 grupos contribuindo | `rejected` |
| Score 80 a 100 em um único grupo, sem limite forte | `two_factor_required` |

Exemplos: aparelho novo isolado soma 20 e aprova; com destinatário desconhecido,
soma 35 e pede 2FA. Valor intermediário (30), contraparte limitada a 25 e desvio
de perfil (25) somam 80 e reprovam. São cenários sintéticos, não taxas de acerto.

`metadata` contém `risk_score`, `risk_level`, motivos e `triggered_rules`, com
pesos, contribuições efetivas, observações, limiares e indicadores de limite forte.
Também salva os totais por grupo e a configuração completa da política.
`risk_level` descreve a faixa do score; a decisão também considera limites fortes.
Dois fatores não são executados pela API; a resposta informa ao integrador o próximo passo.

Pedidos antigos `pix-v1` continuam consultáveis e idempotentes, sem score retroativo.
Use um ID novo para experimentar a política atual. O score cabe no JSONB já
existente, sem migração ou descarte do banco.

Nesta branch, novos IDs também salvam `rule_risk_score` e a avaliação experimental
`gnn`: saída do modelo, modo, contribuição, versão e hash. O modelo usa somente
histórico local anterior ao evento; saída de treino sintético não é probabilidade
validada de fraude. Há uma migração aditiva de índices para bancos existentes.

## Como rodar e testar

Pré-requisito: Docker Desktop com Docker Compose.

```powershell
docker compose up --build --wait
```

API: <http://127.0.0.1:8000>, documentação: <http://127.0.0.1:8000/docs>.
`GET /health_check` retorna 204 sem consultar o banco; `GET /ready` retorna 204
quando a tabela está acessível. `GET /health` mantém `{"status":"ok"}`.
O volume `pix_data` preserva os dados. Para parar, use `docker compose down`.

Se a porta estiver ocupada, copie `.env.example` para `.env` e ajuste `API_PORT`.
`INTERNAL_TOKEN` é configurável; o padrão local é `default_token`.
As rotas Pix exigem o header `INTERNAL-TOKEN` nas duas operações.

### Testes por HTTP

Com a API de pé:

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

Os testes de contrato chamam a API por HTTP, sem importar `src/`. Cobrem contrato, limites,
persistência consultável, regras, normalização, payloads inválidos, autenticação,
repetições e concorrência. Cada cenário usa IDs e pagadores sintéticos próprios;
não apaga dados, mas acrescenta histórico. Testes unitários adicionais verificam
as faixas do score e configurações inválidas. Use uma instalação separada para testes.

Para rodar pytest fora do Docker, com Python 3.12+ e uma API acessível:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:PIX_API_URL = 'http://127.0.0.1:8000'
python -m pytest -v
python -m ruff check src tests scripts
```

Para executar a API fora do Docker, configure `DATABASE_URL` e `INTERNAL_TOKEN`
no ambiente e inicialize seu PostgreSQL com `database/database.sql`. Então rode
`python -m uvicorn src.app:app --reload`. Não há fallback para memória se o banco
estiver indisponível.

### Exemplo do contrato

O payload do enunciado está em [examples/pix.json](examples/pix.json).
No PowerShell:

```powershell
$headers = @{ 'INTERNAL-TOKEN' = 'default_token' }
$payload = Get-Content -Raw examples/pix.json | ConvertFrom-Json
$payload.id = 'pix-score-' + [guid]::NewGuid().ToString('N')
$body = $payload | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/pix/transaction' -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri ('http://127.0.0.1:8000/pix/transaction/' + $payload.id) -Headers $headers
```

Em uma base sem histórico desse pagador, o exemplo retorna `two_factor_required`
com score 30 por `amount_requires_two_factor`. O GET devolve a mesma decisão gravada.

Para demonstrar score 0, 35 e 80 com histórias sintéticas isoladas:

```powershell
python scripts/demo_score.py --url http://127.0.0.1:8000
```

Ou, usando o container de testes já construído:

```powershell
docker compose --profile test run --rm tests python scripts/demo_score.py --url http://api:8000
```

O script usa somente a biblioteca padrão, lê `INTERNAL_TOKEN` do ambiente (padrão
local `default_token`), cria dados novos e confirma as três decisões esperadas.
Não apaga dados. A [resposta de exemplo](examples/scored-response.json) mostra
uma análise completa com score.

| Operação | Resultado |
|---|---|
| `POST /pix/transaction` | 200 com `key`, `status`, `metadata` |
| `GET /pix/transaction/{id}` | 200 com a análise salva ou 404 se o ID não existe |
| Mesmo ID e mesmo payload normalizado | 200 com a decisão original, sem recalcular |
| Mesmo ID e conteúdo diferente | 409, preservando o registro anterior |
| Corpo inválido | 400, sem consumir o ID |
| Token ausente ou incorreto | 403 |
| Falha de banco ou timeout de consulta/trava | 503; repetir com o mesmo ID |

`amount` é um inteiro positivo em centavos: `1050` significa R$ 10,50.
Decimais, booleanos e números em strings são recusados. Datas precisam de fuso;
as contas não podem ter data de abertura posterior ao Pix. O ISPB do destino é
obrigatório, com 8 dígitos. Geolocalização é opcional. Campos desconhecidos são
recusados. IDs têm até 128 caracteres ASCII entre letras, números, `.`, `:`, `_` e `-`.
CPF/CNPJ aceita pontuação e exige 11/14 dígitos, sem consulta cadastral.

As decisões válidas, inclusive rejeições e pedidos de 2FA, ficam gravadas e
consultáveis. Pedidos que não passam pela validação não viram análises Pix.
Erros seguem o formato da referência: `title`, `description`, `translation`, `code`.
O header `X-Request-ID` corresponde ao identificador nos logs JSON.

## Limites conhecidos

A política usa os dados enviados pelo integrador interno e não verifica a identidade
real de contas ou dispositivos. Pedidos históricos são aceitos usando o tempo do
evento; decisões anteriores não mudam quando chega um evento atrasado. As janelas
de consultas têm índices, mas o custo cresce com o histórico de cada pagador.
Token interno, logs e health checks estão implementados; métricas, proteção de
borda e feedback de fraude são evoluções descritas em `docs/architecture.md`.
O nome do grupo e os integrantes ainda precisam ser preenchidos pelo time.
