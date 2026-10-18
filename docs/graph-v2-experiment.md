# Treinamento e comparadores do grafo temporal

O grafo da API é a arquitetura temporal v2, com duas camadas de agregação por
relação, treino em PyTorch e inferência em NumPy. O candidato padrão é
`models/false-positive-v1/gnn-false-positive-v1-seed-42.json`; sua contribuição
é descrita em [gnn-contribution.md](gnn-contribution.md).

## Ferramentas atuais

| Script | Finalidade |
|---|---|
| `train_temporal_gnn.py` | Compara atributos tabulares e grafo direcionado, cada um com sementes 42/43/44, em histórico sintético fornecido completo. |
| `improve_temporal_gnn.py` | Treina candidatos v9 com negativos difíceis e recorte PostgreSQL da API. |
| `calibrate_temporal_gnn.py` | Compara candidatos/comparadores com pesos fixos e calibra novos cortes; não retreina. |
| `demo_temporal_graph.py` | Exporta grafo e decisões de um caso rápido/lento usando explicitamente o comparador fixo 42. |

Treino e avaliação não acontecem nas requisições e não publicam pesos na API.
Trocar pesos ou política impede contribuição até corresponderem a um manifesto
revalidado. O campo `training_evidence_policy` identifica a origem de cada peso.

## Comparadores preservados

Os três arquivos `models/gnn-directed-temporal-v2-seed-*.json` são referências
fixas usadas por scripts e regressões atuais. O relatório
`models/gnn-directed-temporal-v2.metrics.json` registra o benchmark de origem
dessas referências, incluindo comparações de arquiteturas já retiradas do serviço.
Ele não é resultado do treinador atual nem métrica da API vigente.

Esses artefatos permanecem porque `test_temporal_gnn.py`, `test_temporal_case.py`
e os avaliadores usam seus pesos, previsões e paridade. Não são versões alternativas
instaladas na API. Regravá-los para atualizar rótulos destruiria a reprodução.

## Executar um treinamento novo

```powershell
docker compose --profile gnn build gnn-training
docker compose --profile gnn run --rm --no-deps gnn-training python -m scripts.train_temporal_gnn --output models/reproduction/temporal.metrics.json
```

O treinador atual compara seis execuções: duas arquiteturas × três sementes.
Usa 11 categorias, por padrão 440 cenários de treino, 220 de validação e 440 de
teste. Escolhe época por perda BCE de validação e cortes por orçamento de falsos
positivos 0%, 1% e 5%, congelados para teste. A saída é gravada na pasta indicada;
os pesos exportados ficam ao lado do relatório. Não use a pasta dos comparadores
para sobrescrevê-los. A montagem `models/` preserva os resultados no host.

Essa avaliação usa histórico sintético completo, limitado a 300 eventos, que
pode diferir da vizinhança de dois saltos da API. Para reproduzir o candidato
atual com consulta real, siga [falsos positivos](gnn-false-positives.md).

## Propriedades verificadas e limites

Há seis relações: pagar/receber, usar/ser usado por aparelho, possuir/pertencer
ao titular. Arestas históricas de pagamento e aparelho decaem com meia-vida de 12h.
Rejeições não criam pagamento; incrementos próprios são independentes da GNN.
Nenhum rótulo de intenção ou identificador de cenário é atributo do modelo.

Os testes verificam direção, tempo, titularidade, pareamento, deduplicação,
isolamento de conjuntos, pesos finitos, schema, paridade e seleção de limiares.
A rede não mantém memória recorrente de eventos. Os rótulos são artificiais;
os resultados não estimam prevalência, perdas ou eficácia em pagamentos reais.
