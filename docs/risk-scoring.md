# Pesquisa e política de risk score

Consulta às fontes em 17/10/2026. Implementação: `pix-score-v2`.

## O que veio da pesquisa

- A [documentação do Stripe Radar](https://docs.stripe.com/radar/transaction-risk-prevention)
  apresenta score granular, níveis de risco e resultados de avaliação. O produto
  utiliza modelos treinados e dados de rede. Nosso motor usa pontos definidos em
  regras locais; não reproduz esse modelo, seus limiares ou sua acurácia.
- A [documentação do Adyen Protect](https://docs.adyen.com/risk-management/configure-your-risk-profile/)
  distingue regras configuráveis, ações e inspeção dos sinais acionados. Isso
  motivou guardar as evidências e a origem de cada decisão na resposta.
- O [backtesting de regras da Adyen](https://docs.adyen.com/risk-management/configure-your-risk-profile/custom-rules/#backtest-a-rule)
  permite avaliar mudanças contra histórico antes de ativá-las. Aqui há cenários
  sintéticos e testes de fronteira; ainda não há backtesting de uma base rotulada.
- O [Banco Central](https://www.bcb.gov.br/estabilidadefinanceira/pix-seguranca)
  descreve controles para dispositivos cadastrados. Nosso payload não informa
  cadastro de dispositivo: ausência no histórico local não comprova ausência de
  cadastro bancário. O motor usa novidade como sinal heurístico e não implementa
  os limites regulatórios a partir dessa inferência.

Essas fontes orientam a separação entre sinais, score, ação e avaliação da política.
Os pesos, tetos por grupo e limiares abaixo são decisões deste projeto, propostas
para o hackathon. Não são parâmetros fornecidos pela QI Tech nem pelos fornecedores.

## Cálculo reproduzível

1. Avaliar todas as regras sobre o histórico local anterior ao evento, incluindo
   eventos já recebidos com o mesmo timestamp, sem contar o próprio ID repetido.
2. Atribuir o peso configurado a cada sinal acionado.
3. Agrupar os sinais e limitar sua contribuição ao teto do grupo.
4. Somar as contribuições dos grupos e limitar o resultado a 100.
5. Aplicar limites fortes e faixas de decisão.

| Grupo | Sinais e pesos | Teto |
|---|---|---|
| exposure | Valor >= R$ 20.000: 80; valor >= R$ 1.000: 30 | 80 |
| activity | 5 tentativas anteriores em 10 min: 80; soma com atual >= R$ 30.000: 80 | 80 |
| account | Conta de origem com menos de 7 dias: 15 | 15 |
| counterparty | Conta nova sem aprovação anterior: 15; destinatário desconhecido com histórico mínimo: 15 | 25 |
| profile | Valor >= 5 vezes a média anterior: 25 | 25 |
| device | Dispositivo ausente das aprovações anteriores: 20 | 20 |

As condições completas, pisos de valor e amostras mínimas estão no README.
Dentro de cada grupo, maior peso consome o teto primeiro e o código desempata.
Por exemplo, valor alto aciona as duas regras de exposição, mas soma 80, em vez
de 110. Novidade do destino e idade da conta somam no máximo 25, em vez de 30.
Os tetos reduzem duplicação óbvia; não demonstram independência estatística entre grupos.

Faixas: 0..29 aprova; 30..79 pede 2FA; 80..100 rejeita quando ao menos dois grupos
têm contribuição positiva. Um score alto com apenas um grupo e sem limite forte
pede 2FA. O requisito é por grupos, não por quantidade bruta de regras.

Valor individual >= R$ 20.000, sexta tentativa na janela e montante >= R$ 30.000
continuam limites fortes do projeto e sempre rejeitam. O campo `decision_source`
explicita `hard_limit` ou `risk_score`. Não são limites regulatórios universais do Pix.

O limiar 30 permite que novidade isolada de dispositivo (20) siga com pouca fricção,
mas novidade simultânea de dispositivo e destinatário (35) peça confirmação. O
limiar 80 exige acúmulo maior de evidências para reprovação por score. São escolhas
de política verificáveis nos testes, sem estimativa de probabilidade ou de eficácia real.

## Evidências e auditoria

`metadata` salva:

- `risk_score` e `risk_level`: pontos finais e faixa low/elevated/high.
- `score_semantics: heuristic_not_probability`: um score 80 não significa 80% de fraude.
- `triggered_rules`: código, grupo, peso, contribuição antes do teto global,
  valor observado, limiar e indicador de limite forte.
- `raw_score`: soma de todos os pesos antes dos tetos.
- `group_scores`: soma bruta, contribuição efetiva e teto de cada grupo acionado.
- `score_cap_reduction`: desconto do teto global de 100.
- `risk_group_count`, `hard_limits`, `decision_source`, `reasons` e a política completa.

Somar `triggered_rules[*].contribution` e subtrair `score_cap_reduction` reconstitui
`risk_score`. As idades nos detalhes de regras usam segundos; valores monetários
usam centavos e a comparação de perfil usa soma e contagem inteiras.

## Persistência e mudança de comportamento

O score é salvo no mesmo JSONB da decisão, dentro da mesma transação e com as
mesmas travas. Repetir um ID continua retornando exatamente a resposta original.
Uma análise `pix-v1` não ganha score retroativamente nem é reavaliada. Para novos
IDs, sinais fracos isolados que antes pediam 2FA podem ser aprovados; combinações
que antes apenas pediam 2FA podem ser rejeitadas por score. Os limites fortes seguem iguais.

Sem histórico mínimo, o motor não presume aparelho ou recebedor desconhecido como
sinal pontuável. Conta nova continua sendo um dado observado, de peso baixo.
Aprovações locais não confirmam liquidação, legitimidade ou identidade. Podem
contaminar o perfil; não há desconto de score que permita confiança sobrepor limite forte.

## Validação e calibração futura

Os testes verificam os limiares 29/30 e 79/80, combinação de grupos, tetos,
conservação dos pontos, cold start, persistência, repetição e concorrência.
O script `scripts/demo_score.py` cria três cenários e confirma score 0/35/80.

Para calibrar com dados reais, seria preciso obter rótulos confiáveis de fraude,
liquidação e resultado de autenticação; separar treino e avaliação no tempo;
comparar falsos positivos, fraude aprovada, perda em centavos e taxa de 2FA;
então validar pesos e limites contra uma amostra futura. Os testes sintéticos não
medem essas taxas. Reavaliar políticas deve produzir resultados separados, sem
alterar o histórico de decisões já respondidas.
