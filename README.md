# Pix Antifraude — Bootcamp QI Tech 2026

API que analisa um Pix e responde `approved`, `two_factor_required` ou `rejected`,
com score explicável e histórico em PostgreSQL. O score é heurístico (0 a 100),
sem interpretação de porcentagem de fraude. Política atual: `pix-score-v5`.

**Integrantes:** Vinícius Guimarães Drexler, Wallace Dametto Teixeira

## Iniciar

Pré-requisito: Docker Desktop com Docker Compose.

```powershell
docker compose up --build --wait
```

Abra [a documentação interativa](http://127.0.0.1:8000/docs), clique em **Authorize**
e informe o token interno (`default_token` na configuração local).
Selecione um exemplo em **Analisar um Pix**, use um ID novo e execute.
O primeiro Pix de cada pagador exige autenticação adicional.
O exemplo de aprovação pressupõe histórico compatível.

- `POST /pix/transaction`: analisa e grava o Pix.
- `GET /pix/transaction/{id}`: recupera a decisão original.
- `?include_details=true`: inclui histórico consultado, regras, limiares e política.
- `/health_check`: disponibilidade do processo; `/ready`: acesso ao banco.

`amount` é inteiro em centavos: `150000` = R$ 1.500,00. Datas exigem fuso.
`source.channel` informa o canal: `app` ou, por exemplo, `internet_banking` no PC.
O payload completo está em [examples/pix.json](examples/pix.json).
CPF/CNPJ aceita pontuação; o serviço valida o formato, sem consulta cadastral.
Campos desconhecidos são recusados.

## Como a decisão funciona

O motor reúne o histórico pelo documento do pagador, inclusive entre contas,
avalia todas as regras e salva a decisão com suas evidências.

| Fator exibido | O que observa | Pontos padrão / teto |
|---|---|---|
| Histórico inicial | Primeiro Pix ou ausência de referência de valor | 30 / 80; exige 2FA |
| Volume e frequência | Sexta tentativa em 10 min ou total com o Pix atual ≥ R$ 30 mil | 80 / 80; rejeita |
| Idade da conta de origem | Conta aberta há menos de 7 dias | 15 / 15 |
| Destinatário | Conta nova ou destino desconhecido, com pisos e amostra mínima | 15 por regra / 25 |
| Perfil de valores | Valor ≥ 5 × a média de até 10 aprovações anteriores | 80 / 80 |
| Vínculos de dispositivos | Aparelho novo, compartilhamento entre titulares ou vários aparelhos | 20–30 por regra / 40 |
| Canal e horário | App à noite, fora do hábito, com aparelho ou destino desconhecido | 15 / 15 |

A soma dos fatores é limitada a 100. Sem limite forte: score abaixo de 30 aprova;
de 30 a 79 pede 2FA; a partir de 80 rejeita se houver dois fatores contribuindo.
Um único fator, mesmo alto, pede 2FA. Primeiro Pix e ausência de referência pedem
2FA mesmo com o peso do fator zerado; rejeições têm prioridade.

**Referência de valores.** Usa até 10 aprovações anteriores × 5, sem corte por dias.
Sem aprovações, usa apenas a primeira tentativa com 2FA pendente como referência
provisória. Outras pendências e rejeições não aumentam a média. `profile_basis`
identifica a origem nos detalhes. Aprovação local não confirma liquidação ou 2FA.
O limiar de perfil é um sinal de risco, não um limite bancário autorizado.

**Dispositivos.** Em 24 h, o terceiro titular no mesmo aparelho soma 30 pontos;
o terceiro aparelho do pagador, se desconhecido no histórico aprovado, soma 20.
Contam tentativas de qualquer decisão e o aparelho/titular atual. Várias contas
do mesmo titular não contam como várias pessoas. Os sinais compartilham teto de
40 e, isolados, não rejeitam. Uma trava por aparelho protege pedidos simultâneos.

**Horário e canal.** O sinal contextual vale apenas para `app`, das 20h às 6h
em Brasília (UTC−3), em Pix a partir de R$ 500, com três aprovações em 30 dias,
nenhuma noturna e aparelho ou destino desconhecido. Uso habitual ou canal PC
não recebe esses 15 pontos. Isso **não isenta o PC do limite noturno bancário**:
[a IN BCB 512](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=512&tipo=Instru%C3%A7%C3%A3o+Normativa+BCB)
prevê limites por período e regras por perfil. O integrador deve verificar os
limites efetivos da conta, beneficiários e exceções. Esta API não tem esses dados.

## O que o GNN faz

Um GraphSAGE de duas camadas relaciona contas, transferências e aparelhos.
Aprende padrões de vizinhança usando frequência, valores, idades das contas e
compartilhamento de dispositivos. Foi treinado com cenários **sintéticos**,
incluindo operações normais, comerciantes, famílias e redes fraudulentas.
Não consulta dados externos nem aprende durante a requisição.

O padrão `GNN_MODE=shadow` apenas registra o resultado. `off` desliga;
`contribute` permite até 20 pontos experimentais quando o score do modelo ≥ 80.
Esse score não é probabilidade validada de fraude. Histórico: até 30 dias e
300 tentativas relacionadas; faltando dados ou excedendo o limite, o modelo se abstém.
Veja [arquitetura, treino e métricas do GNN](docs/gnn-prototype.md).

## Configurar e entender a resposta

[config/risk-policy.json](config/risk-policy.json) reúne regras, limiares, pesos e tetos.
`factor_weights` usa percentuais de 0 a 200; 100 mantém os pontos.
`weights` define pontos por regra; `group_caps` limita cada fator;
`rule_factors` associa regras a fatores. Peso zero não desativa limites fortes.
`profile_history_size` e `profile_multiplier` controlam a referência de valores;
`device_window_hours`, `device_owner_limit`, `payer_device_limit` e `night_*`
controlam os novos sinais. No Compose, após editar: `docker compose restart api`.
Campos inválidos impedem a inicialização. Mude `version` ao publicar outra política.

A resposta padrão traz score, faixa, origem da decisão, versão, duração e fatores.
Cada fator tem `name` estável para integração, `label` em português, peso, pontos
e regras. `risk_factors_sum` precede o teto global de 100. Os detalhes ficam em
`include_details=true`. O tempo mede a análise antes da gravação e permanece salvo.

**Histórico da conta:** `account_untrust` acumula evidências relevantes por 24 h,
usando o horário de recepção do servidor. A partir de 40 exige 2FA; a partir de
60 retorna `bank_notification.required=true`, com `status=indicated_only`, sem
envio externo. O bloqueio por acumulado a partir de 80 e quatro eventos é optativo
(`untrust.rejection_enabled=false` no padrão), pois a avaliação sintética mostrou
rejeições indevidas adicionais. Não soma ao score da transação e não se autorreforça.
Veja [cálculo, dados e limites](docs/account-untrust.md).

Mesmo ID e conteúdo normalizado retornam a decisão original, sem duplicar histórico.
Conteúdo diferente com o mesmo ID retorna 409. Payload inválido: 400; token ausente
ou incorreto: 403; ID inexistente: 404; banco indisponível ou timeout: 503.
Repetir após 503 deve usar o mesmo ID. Análises antigas conservam sua política.

## Verificar

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests python -m ruff check src tests scripts
docker compose --profile test run --rm tests python scripts/demo_score.py --url http://api:8000
```

Os testes HTTP acrescentam dados sintéticos e cobrem limites, persistência,
idempotência, concorrência, perfis, canais e dispositivos. Use uma base de testes.
O script demonstra scores 0, 35 e 95. O volume `pix_data` preserva o histórico;
`docker compose down` para os serviços sem apagar os dados.

Ajuste porta/token em `.env` conforme [.env.example](.env.example).
Fora do Docker, instale `requirements-dev.txt`, inicialize o PostgreSQL com
`database/database.sql` e configure `DATABASE_URL`, `INTERNAL_TOKEN` e
`RISK_POLICY_PATH=config/risk-policy.json`; execute `python -m uvicorn src.app:app`.
Bases antigas podem aplicar a migração aditiva `database/migrations/002_gnn_graph_indexes.sql`.
Para o acumulado por conta, aplique também `database/migrations/004_account_untrust.sql`.
Essa migração não altera decisões antigas. A migração 003 de permissões é separada
e está preparada para revisão; não é requisito para executar a migração 004.

Detalhes: [política e evidências](docs/risk-scoring.md),
[arquitetura e limites](docs/architecture.md), [GNN](docs/gnn-prototype.md).
[A revisão de práticas bancárias](docs/banking-review.md) registra os controles
implementados e as pendências de produção. O projeto continua sendo demonstrativo.
