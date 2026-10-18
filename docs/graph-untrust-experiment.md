# Avaliador offline de suspeita por vizinhança

[evaluate_graph_untrust.py](../scripts/evaluate_graph_untrust.py) mantém um
experimento heurístico separado da decisão da API. O código atual compara a linha
de base de regras/acumulado com contagem de contatos, vizinhança ponderada e
vizinhança com exigência de repasse. Não carrega um modelo neural nesse avaliador.

## Hipóteses implementadas

A busca usa dois saltos, até dez contatos por conta, janela de 24h, meia-vida
de 12h, atenuação de 0,5 por salto adicional e contato suspeito a partir de 40.
Deduplica caminhos/contas e exclui a origem de sua própria vizinhança.

A contagem simples propõe cinco pontos por contato suspeito, até 20. A fórmula
ponderada usa suspeita/100 e recência, mantendo contatos abaixo de 40 no
denominador. A versão com repasse exige pelo menos dois pares de recebimento e
saída em até 30min, entre 80% e 125% do valor, para outra conta. Uma entrada
suporta no máximo um par. O candidato atual não cria um par histórico.

As propostas de pontos são simulações offline; não são o `contribute` da GNN
ativa. Na API, a rede temporal pode somente elevar aprovação para 2FA, sem
acréscimo de pontos, conforme [gnn-contribution.md](gnn-contribution.md).

## Gerar uma avaliação da política atual

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
docker compose --profile test build tests
docker compose --profile test run --rm --no-deps -v "${PWD}/tmp:/results" tests python -m scripts.evaluate_graph_untrust --output /results/graph-untrust.metrics.json --rows-output /results/graph-untrust.rows.json
```

O replay usa a política atual e simula horário de recepção pela ordem de eventos.
Pendências/rejeições não formam perfil; tentativas não rejeitadas aproximam o fluxo
financeiro, sem comprovar liquidação. Rótulos vêm do gerador, não do grafo.

O relatório separa o gerador geral e os casos relacionais, decisões alteradas,
fricção e ordenação com cortes selecionados na validação. Não altera pesos,
modo, banco ou decisão da API. Médias de vizinhança podem diluir evidências;
contato suspeito não comprova participação da origem em fraude.

Os [testes do experimento](../tests/test_graph_untrust_experiment.py) cobrem
deduplicação, relógios, repasses e isolamento das propostas. Os resultados de
uma política diferente não são apresentados como métricas atuais.
