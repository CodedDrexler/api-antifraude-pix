# GNN combinado com as regras no protótipo

O padrão da aplicação e do Docker Compose é `GNN_V2_MODE=contribute`.
O modelo `gnn-false-positive-v1-seed-42` roda depois das regras, do acumulado
próprio e de `entity_risk`. Se a decisão ainda for `approved`, houver avaliação
completa e o score for **≥75,0977**, a decisão passa a `two_factor_required`.
O corte é o de `score_only_2fa/confidence_budget`, congelado antes do teste no
[experimento de falsos positivos](gnn-false-positives.md).

Essa contribuição é uma escolha explícita para o protótipo do bootcamp. Os
resultados foram obtidos com históricos fictícios; não representam validação
de eficácia em pagamentos reais. Os avaliadores não alteram o modo da API;
a composição do serviço habilita a contribuição explicitamente.

## Composição e limites

- `risk_score` continua sendo o score das regras e, se habilitada para
  contribuir, da camada societária; a rede temporal não acrescenta pontos. Um Pix pode ter score 0 e
  exigir 2FA pelo grafo; `include_details=true` inclui
  **Padrão de risco nas relações entre contas** quando esse controle decide.
- O GNN nunca rejeita sozinho nem remove uma restrição das outras camadas.
  Rejeições, limites fortes e exigências prévias de 2FA têm prioridade.
- A contribuição não acrescenta pontos nem incrementos à conta ou ao titular,
  e não exige notificação bancária por si só. Não há propagação de suspeita
  própria gerada pelo modelo.
- Histórico insuficiente, truncado ou inválido e falha de inferência não geram
  nova restrição. Sem score, `untrust_score` continua omitido. Falha SQL mantém
  o comportamento de erro da aplicação e não vira uma aprovação silenciosa.
- O manifesto [gnn-contribution.json](../config/gnn-contribution.json) vincula
  o corte ao hash do modelo e à configuração completa da política avaliada.
  Outro modelo ou mudança de pesos, janelas ou versão da política desativa a
  contribuição até revalidação. Manifesto ausente/inválido também impede ação;
  a observação pode continuar, com motivo salvo na auditoria.
- GET e reenvio preservam o snapshot original. Ativar ou desativar o grafo não
  recalcula decisões antigas.

Os modos são `off`, `shadow` e `contribute`. A classe de inferência mantém
`shadow` como padrão para experimentos offline; a composição da API escolhe
`contribute`. Para voltar à observação na API:

```dotenv
GNN_V2_MODE=shadow
```

Depois de mudar a configuração, recrie a API com
`docker compose up --build -d api`. Não é necessária migração de banco.

## Auditoria e validação

`decision_metadata.gnn_v2` salva score, hash do modelo, modo, manifesto,
`contribution_status`, `decision_override` e `applied_points=0`. Quando intervém,
`decision_source=gnn_v2` e `decision_causes` identifica a evidência relacional.
O resumo público não expõe modo, manifesto ou pesos internos.

Os [testes da integração](../tests/test_gnn_contribution.py) verificam a fronteira
do corte, ausência de pontos, precedência, abstenção, vínculo com os artefatos,
política diferente, banco real, razão pública e replay. Históricos completos
também são processados com `contribute` ativo, sem formar referência aprovada a
partir das novas pendências e sem alimentar o acumulado com o próprio GNN.

A coleta da suíte atual identifica **691 casos**, incluindo **45 casos** de
contribuição. A execução e seus resultados são registrados no
[inventário](testes-politicas.md). Esses casos incluem
reprodução do comportamento do corte congelado e os cenários legítimo/suspeito
por HTTP, com dados de teste isolados do banco principal.

O teste sintético maior anterior simulava a intervenção sobre uma linha de base
congelada. As regressões integradas agora verificam alguns históricos com a
contribuição ativa do início ao fim; não repetem uma avaliação populacional
completa desse ciclo. Novas pendências podem reduzir a referência de aprovações
e influenciar requisições futuras. Isso permanece uma limitação a acompanhar,
junto aos falsos positivos das próprias regras e à ausência de confirmação
de 2FA ou liquidação neste projeto.
