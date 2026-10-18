# Pix Antifraude: motivos das políticas

8 slides de conteúdo: aproximadamente 6min40s. Perguntas: 3 minutos.

## 1. Organização para facilitar a evolução (30s)

Somos Vinícius Guimarães Drexler e Wallace Dametto Teixeira. Escolhemos uma estrutura parecida com a do primeiro desafio porque ela segue boas práticas de organização e facilita a manutenção. O motivo dessa escolha também tem relação com a política de risco: precisamos conseguir revisar uma decisão e ajustar uma regra com clareza. Nesta apresentação, o foco são os motivos das políticas de decisão e das condições para flexibilizá-las.

## 2. Proteção com o menor atrito necessário (40s)

Nossa política procura equilibrar duas consequências: deixar passar uma operação de risco e interromper um pagamento legítimo. Uma conta recente, um aparelho novo ou um destinatário desconhecido podem ter explicações normais. Por isso pesquisamos práticas de prevenção a fraude e orientações do Banco Central, e estruturamos 13 regras para avaliar comportamento, valor e contexto. Os pesos e limites são escolhas do protótipo. Queremos reservar intervenções mais fortes para evidências mais fortes e usar confirmação adicional quando a informação ainda é insuficiente. Isso organiza as decisões sem transformar toda novidade em uma rejeição.

## 3. Aprovar, confirmar ou rejeitar (65s)

Definimos três respostas para graduar a intervenção. Aprovar preserva a experiência quando não existe motivo suficiente para restringir. Pedir autenticação adicional permite verificar uma situação incerta sem rejeitá-la de imediato. Rejeitar atende limites fortes ou uma combinação intensa de fatores de risco. Na política atual, score a partir de 30 exige 2FA. A rejeição por score exige pelo menos 80 pontos e dois fatores positivos. Um fator isolado com 80 pede 2FA. A sexta tentativa ou R$ 30 mil acumulados em dez minutos são limites fortes e têm prioridade. Sem referência aprovada, valores a partir de R$ 500 exigem 2FA. Histórico acumulado e GNN também podem exigir confirmação, inclusive em uma operação com score baixo. Os valores são parâmetros do protótipo. A API solicita autenticação, mas não confirma que ela ocorreu.

## 4. Por que combinar sinais no risk score (45s)

O risk score organiza a intensidade e a combinação dos sinais para evitar decisões desproporcionais. Um aparelho novo pode representar uma troca legítima. Com valor e histórico elegíveis, ele soma 20 pontos e, sozinho, não exige rejeição. Se o destinatário também for desconhecido, a soma chega a 35 e exige confirmação adicional. O peso de cada sinal representa uma escolha da equipe sobre o risco que merece atenção. Limitamos contribuições por fator para conter a sobreposição de regras parecidas. Também exigimos pelo menos dois fatores positivos para rejeitar por score. Esses fatores não representam independência estatística comprovada. O score é heurístico, entre zero e cem, e não uma probabilidade de fraude.

## 5. Quando o histórico permite flexibilizar (60s)

Tratamos negociação como flexibilização condicionada a evidências. Um valor alto em relação ao perfil geral pode ser habitual para aquele destinatário, como um pagamento recorrente. Nesse caso, o histórico da relação pode justificar retirar somente os pontos do desvio de valor. Exigimos cinco amostras do pagador e três da relação, em pelo menos dois dias distintos de recebimento, além de valor entre metade e o dobro da mediana da relação. Isso evita conceder uma exceção ampla com histórico escasso ou criado em uma rajada. Somente aprovações anteriores formam a referência de valores: rejeições e pendências não elevam o padrão. A flexibilização não elimina limites fortes, sinais de aparelho, acumulado ou exigência do grafo. Não há negociação dinâmica de limites com o cliente. O operador define as condições previamente.

## 6. Quando manter a restrição (55s)

A confiança tem limites porque familiaridade não elimina risco. A sexta tentativa ou o montante de R$ 30 mil em dez minutos rejeitam mesmo com destinatário conhecido. Repetir comportamentos de risco também merece atenção, por isso a conta reúne evidências próprias por 24 horas. A partir de 40 há 2FA e a partir de 60 há indicação de aviso ao banco, sem envio automático. Optamos por manter desativado o bloqueio baseado apenas nesse acumulado, para limitar a consequência de sinais heurísticos repetidos. Cada evidência expira individualmente. Sinais do destinatário e da GNN não viram suspeita própria do pagador. Isso evita que uma relação, por si só, contamine sua avaliação e que a própria restrição gere suspeita indefinidamente. A decisão deve acompanhar a evidência atribuível à conta.

## 7. Por que a GNN complementa as regras (50s)

Uma operação pode parecer normal isoladamente e fazer parte de uma sequência relacional que merece investigação. Essa é a razão de incluir a GNN: acrescentar a visão da rede de transações, incluindo direção e tempo, para investigar padrões como recebimentos seguidos de repasses rápidos. Ela já participa das decisões do protótipo. Se as demais camadas aprovarem e houver avaliação completa com score relacional a partir de 75,0977, pode exigir 2FA. Escolhemos limitar sua intervenção à confirmação adicional porque o modelo usa dados sintéticos e ainda existe incerteza sobre intenções legítimas parecidas. A GNN não rejeita sozinha, não relaxa restrições anteriores e não soma pontos ao risk score. Modelo, política e corte precisam corresponder aos artefatos avaliados. O sinal relacional pede verificação, sem afirmar fraude.

## 8. Por que validar antes de ampliar a intervenção (55s)

Uma política pode aumentar alertas e também interromper mais pagamentos legítimos. Por isso avaliamos ganho e fricção em conjunto. Com apoio de IA, construímos casos positivos, negativos e combinações das regras, incluindo situações pensadas como falsos positivos. A documentação registra 691 testes aprovados com a GNN contribuindo. Eles verificam o comportamento esperado, sem estimar a taxa de fraude real. Para a GNN, a meta inicial era menos de 10% de falsos positivos. Adotamos depois um critério mais rigoroso: limite superior nominal de 95% de até 1% para desafios adicionais em legítimos aprováveis, além de ganho nos positivos. No teste sintético com 1.800 cenários, cada candidato da calibração conservadora gerou zero desafios indevidos entre 1.064 legítimos aprováveis. A equipe habilitou 2FA no protótipo. Ampliar a intervenção exige resultados confirmados e acompanhamento de falsos positivos.

## 9. Perguntas (180s)

Reservar três minutos para perguntas sem exibir a duração. Por que 2FA? Para tratar incerteza com uma intervenção intermediária. O cliente negocia limites na hora? Não. A flexibilização segue critérios prévios definidos pelo operador. O histórico pode apagar qualquer risco? Não. Pode atenuar somente o desvio de valor nas condições da confiança contextual. A GNN já atua? Sim, pode elevar aprovação para 2FA, sem rejeição própria. Os números provam eficácia real? Não, os resultados de avaliação são sintéticos. O motor solicita 2FA, mas não confirma autenticação nem liquidação.

## Políticas de decisão e flexibilização

Negociação significa condições de intervenção e de atenuação previamente definidas pelo operador. Não há negociação dinâmica com o cliente. Os números abaixo são parâmetros do protótipo.

| Política | Por que existe | Condição atual | Flexibilização e limites |
|---|---|---|---|
| Aprovar | Preservar pagamentos sem motivo suficiente de restrição | Nenhum controle exige 2FA ou rejeição | Score baixo não supera restrição do acumulado ou da GNN |
| Pedir 2FA | Verificar incerteza com intervenção intermediária | Score ≥30, ou sem referência aprovada e valor ≥R$500, ou controles adicionais | A API solicita, mas não executa nem confirma a autenticação |
| Rejeitar | Conter risco elevado ou exposição excessiva em curto intervalo | Score ≥80 e ≥2 fatores, ou sexta tentativa/≥R$30 mil em 10 min | Histórico familiar não remove limites fortes |
| Limitar pontuação por fator | Conter sobreposição de sinais parecidos | Tetos por fator e score total até 100 | Mais regras no mesmo fator não criam um segundo fator |
| Atenuar desvio de valor | Reconhecer um pagamento habitual naquela relação | ≥5 amostras do pagador, ≥3 da relação em ≥2 dias distintos de recebimento, valor de 50%–200% da mediana | Zera somente o desvio de perfil. Outros controles permanecem |
| Formar referência de valores | Evitar que rejeições e pendências elevem o padrão | Somente aprovações anteriores | Aprovação local ainda não confirma liquidação ou legitimidade |
| Acumular evidências próprias | Tratar repetição de comportamentos atribuíveis à conta | Janela de 24h. ≥40 exige 2FA. ≥60 indica aviso | Bloqueio pelo acumulado desligado. Sinais do destino e da GNN não alimentam suspeita própria |
| Usar a GNN | Acrescentar contexto da rede que uma operação isolada não mostra | Aprovação prévia, avaliação completa, score do grafo ≥75,0977 e artefatos válidos | Apenas eleva aprovação para 2FA. Não rejeita sozinha nem altera risk_score |
| Rever a política | Avaliar ganho junto do impacto em legítimos | 691 testes documentados e avaliação sintética com conjuntos separados | Trocar modelo ou política exige revalidação da contribuição |

Fontes: docs/politicas-negocio.md, docs/gnn-contribution.md, docs/contextual-trust.md, docs/account-untrust.md e config/risk-policy.json.
