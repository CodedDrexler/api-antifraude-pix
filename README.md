# Pix Antifraude — Bootcamp QI Tech 2026

**Integrantes:** Vinícius Guimarães Drexler e Wallace Dametto Teixeira.

API em Python 3.12, FastAPI e PostgreSQL 16 que recebe um Pix e retorna
`approved`, `two_factor_required` ou `rejected`, com motivos e histórico persistidos.
Política atual: **`pix-score-v8`**. O score de 0 a 100 é heurístico, sem representar
probabilidade de fraude.

## Como o motor de decisão funciona

O fluxo segue as camadas do Base Service: validação → resource HTTP → controller
→ repository/histórico → regras puras → decisão → gravação com commit.
O histórico do pagador é agregado por CPF/CNPJ, inclusive entre contas. Cada
consulta respeita sua janela e exclui informações ainda indisponíveis na análise.

A tabela [`pix_analysis`](database/database.sql) guarda pedido normalizado,
hash, decisão, evidências, política e datas do evento e do recebimento. Índices
por documento, conta, destinatário e dispositivo atendem às consultas; IDs únicos,
travas e proteção contra alteração preservam consistência e auditoria.
Reenviar o mesmo ID e conteúdo recupera a decisão original; conteúdo diferente
gera **409**. Pedidos inválidos não geram análise.

## Regras

Parâmetros são hipóteses demonstrativas, escolhidas para testar fronteiras e
combinações explicáveis; não foram calibrados com fraude real. Familiaridade
significa aprovação local nos últimos **30 dias**. Os pisos de **R$ 500** reduzem
fricção em valores menores; **3 aprovações** dão uma referência mínima de uso.

| Regra | Lógica | Parâmetros padrão | Por quê |
|---|---|---|---|
| Frequência | Rejeita a sexta tentativa na janela | 5 anteriores em 10 min; 80 pontos e limite forte | Conter rajadas, contando também recusas e pendências |
| Montante | Rejeita quando a soma, incluindo o Pix atual, alcança o teto | ≥ R$ 30 mil em 10 min; 80 pontos e limite forte | Conter saída concentrada sem consulta externa |
| Primeiro Pix | Exige 2FA sem tentativas anteriores | 30 pontos | Evitar aprovação sem referência |
| Referência ausente | Exige 2FA se há tentativas, mas falta referência elegível de valor | 30 pontos | Recusas anteriores não formam perfil confiável |
| Origem recente | Pontua conta com pouca idade | < 7 dias; +15 | Tratar pouca experiência como sinal complementar |
| Destino recente | Pontua destino desconhecido e recém-aberto | < 7 dias, valor ≥ R$ 500; +15 | Combinar novidade com exposição financeira |
| Destino desconhecido | Pontua contraparte fora do histórico aprovado | ≥ 3 aprovações, valor ≥ R$ 500; +15 | Comparar com o hábito do pagador sem bloquear novidade isolada |
| Desvio de perfil | Compara valor com a média das últimas aprovações | ≥ 5 × média de até 10 aprovações; +80 | Detectar salto expressivo com amostra curta e reproduzível |
| Aparelho desconhecido | Pontua dispositivo sem aprovação prévia | ≥ 3 aprovações, valor ≥ R$ 500; +20 | Sinalizar mudança de acesso com exposição relevante |
| Aparelho compartilhado | Conta titulares distintos, incluindo o atual | ≥ 3 titulares em 24 h; +30 | Investigar compartilhamento sem confundir várias contas do mesmo titular |
| Rotação de aparelhos | Pontua aparelho desconhecido com diversidade recente | ≥ 3 aparelhos em 24 h, incluindo o atual; +20 | Identificar troca concentrada sem penalizar uso familiar |
| App noturno atípico | Exige ausência de hábito noturno e aparelho ou destino novo | 20h–6h UTC−3, ≥ 3 aprovações, ≥ R$ 500; +15 | Somar contexto; horário sozinho não determina risco |
| Possível duplicidade | Mesmas contas e valor, outro ID, após aprovação ou pendência | Até 120 s; +30 e aviso na resposta | Pedir confirmação em possível reenvio sem afirmar pagamento liquidado |

Sem aprovações, a primeira tentativa pendente de 2FA é a referência provisória
de valor; novas pendências não a elevam. Isso permite demonstrar formação de perfil,
mas não comprova autenticação. A janela de 10 min captura concentração; 24 h cobre
diversidade recente; 7 dias representa conta nova; 120 s captura repetição imediata.
Esses cortes precisam de validação antes de uso real.

**Confiança por relação:** a v8 pode zerar somente os pontos do desvio de perfil
quando há ≥ 5 aprovações gerais, ≥ 3 para o destino e ≥ 2 dias distintos de
recebimento, usando até 20 amostras em 30 dias. O valor deve estar entre 0,5 e 2 ×
a mediana da relação. Repetição e dias distintos evitam criar confiança numa única
rajada; mediana reduz influência de extremos. Os outros controles continuam ativos.
[Critérios e testes](docs/contextual-trust.md).

## Como as regras viram decisão

Os pontos recebem o peso percentual configurado, com descarte da fração, e são
limitados por fator: histórico inicial **80**, atividade **80**, origem **15**,
contraparte **25**, perfil **80**, dispositivos **40**, horário **15** e duplicidade
**30**. A soma tem teto **100**. Isso limita sinais correlacionados; os pesos
padrão dos fatores são 100%.

| Prioridade | Condição | Decisão |
|---|---|---|
| 1 | Limite forte de frequência ou montante | `rejected` |
| 2 | Score ≥ 80 e pelo menos dois fatores positivos | `rejected` |
| 3 | Primeiro Pix, referência de valor ausente ou score ≥ 30 | `two_factor_required` |
| 4 | Demais casos | `approved` |

O corte **30** permite confirmar uma dúvida relevante; **80 + dois fatores** exige
corroboração para rejeitar. Um desvio de perfil isolado, mesmo com 80, pede 2FA.
Limites fortes e 2FA inicial continuam válidos com pesos zerados.

**Suspeita acumulada (`account_untrust`):** usa evidências próprias de frequência,
montante, perfil e dispositivos em 24 h pelo relógio do servidor. Quando o score
alcança 30, soma `ceil(pontos elegíveis / 4)`, até 25 por evento; limite forte soma
25. O divisor e o teto evitam transportar integralmente o score para o acumulado.
Total ≥ 40 exige 2FA; ≥ 60 indica aviso, sem enviá-lo. O bloqueio optativo em 80
com ≥ 4 eventos fica **desativado**: o experimento acrescentou recusas legítimas
sem ganho de detecção. Sinais do destino e do grafo não viram suspeita própria;
o acumulado não é somado ao score nem relaxa uma recusa.
[Cálculo e limites](docs/account-untrust.md).

**Camadas experimentais:** GNN v1, grafo v2 direcionado/temporal e risco por titular
e vínculos societários rodam em `shadow` por padrão: registram evidências sem mudar
a decisão. O v2 aceita apenas `shadow` ou `off`. V1 e `entity_risk` aceitam também
`contribute`, compartilhando teto relacional de +20; vínculos verificados podem
propor 2FA pelos [critérios documentados](docs/entity-risk.md). O cadastro do operador
começa vazio e exige configuração; não há consulta automática à Receita ou DICT.

## Como rodar e testar

Requer Docker Desktop com Docker Compose. Na raiz do projeto:

```powershell
docker compose up --build -d --wait
```

Abra o [Swagger](http://127.0.0.1:8000/docs), escolha um exemplo em **Analisar um Pix**
e use um ID novo. O primeiro Pix exige 2FA. Porta e modos experimentais podem ser
definidos em `.env`, conforme [.env.example](.env.example).
`docker compose down` encerra os serviços e preserva o volume `pix_data`.

| Método e rota | Resultado |
|---|---|
| `POST /pix/transaction` | Grava pedido válido inédito e retorna `key`, `status`, `metadata` |
| `GET /pix/transaction/{id}` | Recupera a análise pelo ID enviado, com a política original |
| `GET /health_check` ou `/health`; `GET /ready` | Verifica processo; verifica acesso ao banco |

Contrato: [pedido completo](examples/pix.json). `amount` é inteiro em centavos
(`150000` = R$ 1.500); datas exigem fuso; CPF/CNPJ aceita pontuação com validação de
formato; campos desconhecidos são recusados. A metadata explica score, fatores,
origem, versão e duração da análise; `?include_details=true` acrescenta evidências
e política salvas. Rotas Pix não exigem token. Erros: **400** entrada inválida,
**404** ID ausente e **503** banco indisponível/timeout; após 503, repita o mesmo ID.

**Suíte isolada no Windows:** execute `.\testar.bat --no-pause` ou dê dois cliques
em [testar.bat](testar.bat). O script cria API e banco temporários, executa testes,
lint e formatação e remove apenas os recursos dessa execução. O GitHub Actions
executa as mesmas verificações de testes e qualidade a cada push/PR.

**Demonstração dos três resultados:** os comandos abaixo inserem dados sintéticos;
use uma instalação dedicada à demonstração.

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests python scripts/demo_score.py --url http://api:8000
```

**Sem Docker:** Python 3.12 e PostgreSQL 16; instale
`pip install -r requirements-dev.txt`, inicialize [database.sql](database/database.sql),
configure `DATABASE_URL` e `RISK_POLICY_PATH=config/risk-policy.json` e execute
`python -m uvicorn src.app:app`.

**Base existente:** o SQL inicial só roda em banco novo. Aplique as
[migrações](database/migrations) pendentes para sua versão, incluindo 006 e 007
para os novos históricos; a 003 trata de permissões e requer configuração própria.
Para política, edite [risk-policy.json](config/risk-policy.json), incremente `version`
e reinicie a API. Para atualizar código/modelos, reconstrua com o comando inicial.

## Resultados e como foram alcançados

Verificação de **18/10/2026**: **493 testes aprovados, nenhum ignorado**, com API e
PostgreSQL isolados; lint aprovado e **77 arquivos Python** com formatação válida.
Testes cobrem limites, pares com uma mudança de contexto, concorrência, histórico
temporal, persistência, replay de IDs e separação entre risco próprio e relacional.

| Resultado | Como foi alcançado |
|---|---|
| Score **0 → aprovação**, **35 → 2FA**, **95 → rejeição** | Demo HTTP prepara histórico; combina aparelho novo + destino novo (20 + 15), ou desvio de perfil + destino novo (80 + 15) |
| Valor habitual para um destino pode deixar de parecer anomalia geral | Testes da v8 comparam perfil geral e mediana por relação, exigindo amostra e dias distintos |
| Acumulado preservado sem bloqueio automático | Comparação de 150 cenários de validação e 200 de teste não mostrou intervenção adicional em fraude sintética; bloqueio optativo acrescentou 4 recusas legítimas no teste |
| Grafo v2 sinalizou **146–163/200** origens de risco e **0–7/240** legítimas no teste | 440 cenários de treino, 220 de validação e 440 de teste; identidades/datas separadas, três sementes e limiar escolhido na validação com orçamento de 1% de falsos positivos |

No experimento offline v2, **71–81** origens de risco e **0–1** legítimas passaram
a exigir 2FA; sinalizar não equivale a mudar a decisão. Houve falsos positivos acima
de 1% no teste em uma semente. Os pesos foram treinados com a política v7; a API
v8 os usa somente em observação. Esses números sintéticos não medem eficácia da
integração nem desempenho em produção.

Reprodução, comparações e métricas: [casos parecidos e acumulado](docs/decision-contrasts.md),
[experimento v2](docs/graph-v2-experiment.md), [integração v2](docs/graph-v2-api.md) e
[risco do titular](docs/entity-risk.md). [Apresentação](apresentacao/Pix-Antifraude.pptx)
disponível para a exposição de até 7 minutos prevista no desafio.

Detalhes: [regras e evidências](docs/risk-scoring.md), [arquitetura](docs/architecture.md),
[auditoria histórica](docs/antifraud-audit.md) e [pendências de produção](docs/banking-review.md).
O projeto não executa 2FA, liquidação, envio de avisos ou gestão de limites bancários.
Aprovação local não confirma pagamento; não há validação com fraude real.
