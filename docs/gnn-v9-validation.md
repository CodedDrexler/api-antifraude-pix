# Validação do GNN na política v9

A contribuição do grafo depende de benefício incremental e controle de intervenções
indevidas. O avaliador em [validate_temporal_gnn.py](../scripts/validate_temporal_gnn.py)
compara propostas sem alterar a API, seus pesos ou decisões salvas. O modo disponível
na API permanece `shadow` ou `off` durante a avaliação.

## Resultado de 18/10/2026

**A contribuição não foi habilitada.** As duas propostas foram avaliadas com os
mesmos 550 cenários de calibração e 1.100 de teste, usando a política v9 e a
consulta PostgreSQL real. O teste contém 500 positivos e 600 legítimos sintéticos.
Os intervalos abaixo representam resultados dos três modelos separados, sem
somar os mesmos cenários três vezes.

| Proposta | Positivos com 2FA adicional / 500 | Legítimos com 2FA indevido / 600 | Taxa de fricção adicional | Maior limite superior nominal de 95% |
|---|---:|---:|---:|---:|
| Somente score | 389–417 | 14 em cada modelo | 2,33% | 3,88% |
| Score + valor mínimo + dois repasses rápidos | 134–154 | 1–2 | 0,17–0,33% | 1,21% |

As propostas não acrescentaram rejeições e obtiveram score nos 1.100 cenários.
Os falsos positivos concentraram-se em comerciantes com liquidação rápida:
14 de 100 com somente score e 1–2 de 100 com os filtros adicionais.

Na proposta filtrada, as sementes 42 e 44 passaram nos critérios numéricos do
teste principal, mas a 43 não demonstrou o limite superior de 1% exigido: seu
intervalo nominal chegou a 1,21%. Não foi escolhido um vencedor depois do teste.
Os limiares por modelo e os resultados completos estão no
[relatório agregado](../models/gnn-v9-validation.metrics.json).

O complemento com o contrato do bootcamp expôs outra limitação: o histórico
fictício de liquidação comercial legítima recebeu **99,95 pontos no modelo 42**,
e as duas propostas pediriam 2FA nos três modelos. O pagamento habitual e o
destinatário novo sem outros riscos foram preservados. O cenário de origem
suspeita seria sinalizado pelas sementes 42/43, mas não pela 44.
Esses cinco casos ilustram comportamento; não estimam uma taxa de erro populacional.
Veja o [relatório dos exemplos do bootcamp](../models/gnn-v9-bootcamp.metrics.json).

O ganho nos cenários artificiais existe, e os filtros reduzem bastante os falsos
positivos. Ainda assim, o resultado não sustentou ativação automática nem para o
protótipo com o critério adotado. O modo `shadow` foi preservado, incluindo uma
regressão que verifica a aprovação do comerciante mesmo com score acima de 99.
O próximo experimento precisaria distinguir liquidação comercial legítima com
novos atributos verificáveis e um novo teste, sem reajustar cortes sobre este.

## Desenho definido antes da medição

- Três modelos já exportados, sementes 42, 43 e 44; nenhum vencedor é escolhido no teste.
- 550 cenários de calibração e 1.100 de teste, em 11 categorias. As sementes dos cenários
  começam em 710000 e 910000, fora das faixas do treino original. A calibração usa maio
  e o teste usa setembro. Rótulos representam a intenção sintética do gerador.
- O controlador real processa cada evento em ordem cronológica, incluindo score,
  confiança por relação e acumulado próprio. O recebimento simulado acompanha o evento.
- A inferência usa a consulta PostgreSQL da API, com dois saltos e seus limites reais.
  Uma avaliação adicional com todo o histórico é apenas um diagnóstico da diferença.
- Cada cenário roda dentro de uma transação externa descartada ao terminar. Commits
  internos do controlador usam savepoints. Não há gravação no banco principal.
- A linha de base usa regras v9 e acumulado próprio. A contribuição de `entity_risk`
  fica desligada para isolar o efeito do GNN.

O teste é exploratório. O gerador continua sendo da mesma família artificial usada
no treinamento; sementes novas não equivalem a novas populações ou fraude confirmada.
Há pares temporais relacionados, e os três modelos são avaliados nos mesmos eventos.
Por isso, seus resultados não são somados como observações independentes.

O material disponível do bootcamp é o contrato em `examples/pix.json`, sem rótulo
de fraude confirmado. O complemento [bootcamp_graph_cases.py](../scripts/bootcamp_graph_cases.py)
parte desse pedido de R$ 1.500 e acrescenta históricos fictícios explícitos:
pagamento habitual, destinatário novo, liquidação rápida legítima e uma origem
com remetentes de risco. O primeiro Pix sem histórico também é verificado.
Os rótulos desses históricos são hipóteses dos cenários. Os cinco exemplos
reutilizam os limiares congelados, sem selecionar novos pesos ou cortes, e não
entram na estimativa populacional das taxas do teste maior.

## Propostas comparadas

| Proposta | Condições para acrescentar uma intervenção |
|---|---|
| `score_only_2fa` | Decisão original aprovada e score do grafo acima do limiar |
| `corroborated_2fa` | As condições anteriores, valor a partir de `no_history_min_amount` e pelo menos dois pares de repasse rápido |

Ambas só propõem `approved → two_factor_required`. Não acrescentam pontos,
rejeições ou suspeita própria; não alteram decisões já restritas. Uma avaliação
indisponível não propõe ação. Não é simulado o sucesso da autenticação adicional.

Os pares rápidos são um atributo construído do mesmo histórico que o modelo usa,
não uma confirmação externa independente de fraude. A comparação serve para medir
se essa exigência adicional reduz a fricção nos cenários legítimos.

Para cada modelo/proposta, o limiar maximiza novos casos sintéticos positivos na
calibração com até 1% de novos desafios entre os legítimos que a linha de base
aprovaria. O denominador não inclui pagamentos já recusados ou pendentes de 2FA.
Os limites são congelados antes de gerar e avaliar o teste. Não se reajusta o
limiar depois de ver seus resultados.

Separar treinamento, escolha do limiar e avaliação reduz o risco de sobreajuste:
[documentação de limiares do scikit-learn](https://scikit-learn.org/stable/modules/classification_threshold.html).

## Critérios de decisão

Cada uma das três sementes precisa cumprir todos estes critérios na proposta:

1. Acrescentar intervenção em pelo menos 5% dos positivos sintéticos totais.
2. Limite superior do intervalo nominal de 95% de Wilson para novos desafios
   em legítimos aprováveis não ultrapassar 1%.
3. Nenhuma categoria legítima ter mais de 5% de desafios adicionais.
4. Não gerar rejeições adicionais.
5. Produzir avaliação em pelo menos 95% dos cenários.

Os intervalos são estimativas binomiais nominais, sem corrigir a dependência entre
cenários pareados. São uma verificação adicional de tamanho de amostra, não uma
garantia de operação real. Os critérios de 1%, 5% e 95% são hipóteses de engenharia
definidas para este experimento, sem calibração bancária ou caráter regulamentar.

Passar os critérios sintéticos permite investigar uma proposta. Ativá-la em
pagamentos reais também exige resultados confirmados, avaliação prospectiva,
medição de perdas/fricção e acompanhamento de mudança de distribuição. Esse
experimento não produz esses dados nem ativa contribuição automaticamente.

## Como interpretar falsos positivos

O relatório separa:

- Matriz de confusão da proposta de intervenção em todos os casos sintéticos.
- Novos desafios de 2FA entre legítimos que seriam aprovados pela linha de base.
- Ganho de intervenção em positivos que a linha de base aprovaria.
- Recusas adicionais, cobertura e resultados por categoria.

Solicitar 2FA não comprova detecção de fraude. A prevalência artificial também
não estima a precisão no Pix real. Por exemplo, em 100 mil operações hipotéticas,
com fraude em 0,1%, recall de 80% e falsos positivos de 1%, seriam 80 alertas
corretos e 999 incorretos: aproximadamente 7,4% de precisão. Os números são uma
ilustração matemática, não uma estimativa de prevalência ou desempenho do projeto.
[Definições de precisão, recall e falsos positivos](https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall).

## Proteções que já existem na API

- Pontos limitados por fator para conter sinais correlacionados; rejeição por
  score exige pelo menos dois fatores positivos. Limites fortes têm prioridade.
- Valor e histórico mínimo contextualizam sinais de aparelho, destino e horário.
  Sem perfil aprovado, somente valores a partir do limite configurado exigem 2FA
  por ausência de referência; as demais regras continuam ativas.
- Confiança por relação pode reduzir apenas o desvio de valor, com aprovações
  suficientes, dias distintos e valor compatível com a mediana daquela relação.
- Histórico futuro é excluído; informação indisponível na recepção não é usada.
  Os próprios incrementos expiram e não incorporam a suspeita dos destinatários.
- O grafo abstém-se quando faltam dados, seus limites são excedidos ou a
  inferência falha. Sua saída não é convertida em probabilidade de fraude.
- O modo `shadow` impede que falsos alarmes experimentais mudem a decisão.

Essas proteções reduzem fontes conhecidas de erro; não comprovam uma taxa de
falsos positivos sem uma avaliação com resultados reais.

## Reprodução

Use somente um projeto Compose descartável. O comando `run` abaixo não inicia a
API porque a avaliação chama o controlador diretamente:

```powershell
docker compose -p bootcamp-gnn-validation up -d --wait db
docker compose -p bootcamp-gnn-validation --profile test build tests
docker compose -p bootcamp-gnn-validation --profile test run --rm --no-deps -v "${PWD}/models:/results" tests python -m scripts.validate_temporal_gnn --output /results/gnn-v9-validation.metrics.json
docker compose -p bootcamp-gnn-validation down --volumes --remove-orphans
```

Não aponte `PIX_TEST_DATABASE_URL` para o banco principal. O avaliador não treina
modelos, não substitui pesos e não altera a configuração do serviço. Linhas por
cenário podem ser exportadas com `--rows-output`, se necessário; por padrão só o
[relatório agregado](../models/gnn-v9-validation.metrics.json) é preservado.

Para executar o complemento do contrato antes de encerrar o banco descartável:

```powershell
docker compose -p bootcamp-gnn-validation --profile test run --rm --no-deps -v "${PWD}/models:/results" tests python -m scripts.bootcamp_graph_cases --threshold-report /results/gnn-v9-validation.metrics.json --output /results/gnn-v9-bootcamp.metrics.json
```
