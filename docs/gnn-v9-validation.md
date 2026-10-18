# Avaliador de propostas do GNN na política v9

O script [validate_temporal_gnn.py](../scripts/validate_temporal_gnn.py) processa
históricos pelo controlador e pela consulta PostgreSQL reais. Compara propostas
de intervenção sobre uma linha de base sem contribuição da GNN. Seus serviços
de inferência usam `shadow`; isso não altera o padrão `contribute` da API.

## Propostas e medição

| Proposta | Condição para aprovação → 2FA |
|---|---|
| `score_only_2fa` | Avaliação disponível e score no limiar congelado. |
| `corroborated_2fa` | Mesma condição, valor ≥ `no_history_min_amount` e ≥dois pares de repasse rápido. |

Não há pontos, rejeições adicionais, redução de restrições ou incremento próprio
nessas propostas. O avaliador usa explicitamente os três comparadores fixos em
`models/gnn-directed-temporal-v2-seed-*.json`; não avalia automaticamente o modelo
42 padrão da API. Para os candidatos atuais, use a [calibração conservadora](gnn-false-positives.md).

Os conjuntos padrão têm 550 cenários de calibração e 1.100 de teste, em 11
categorias, com faixas de sementes/datas separadas. Cada cenário usa transação
externa descartada; commits do controller tornam-se savepoints. O horário
de evento simula a recepção. `entity_risk` fica desligado para isolar o efeito.

O limiar é escolhido na calibração com orçamento pontual de até 1% de novos
desafios entre legítimos aprováveis. É congelado antes do teste. O relatório
separa matriz de confusão, ganho incremental, fricção, rejeições e cobertura.

Os critérios por semente são: ganho ≥5% dos positivos; limite superior nominal
de Wilson 95% da fricção ≤1%; fricção por categoria legítima ≤5%; nenhuma rejeição
adicional; cobertura ≥95%. São critérios do experimento, sem calibração bancária.
O teste não escolhe uma semente vencedora nem habilita contribuição.

## Reprodução

Use banco descartável e pasta de saída separada. Crie `tmp` antes do mount:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
docker compose -p pix-gnn-validation up -d --wait db
docker compose -p pix-gnn-validation --profile test build tests
docker compose -p pix-gnn-validation --profile test run --rm --no-deps -v "${PWD}/tmp:/results" tests python -m scripts.validate_temporal_gnn --output /results/gnn-v9-validation.metrics.json
docker compose -p pix-gnn-validation --profile test run --rm --no-deps -v "${PWD}/tmp:/results" tests python -m scripts.bootcamp_graph_cases --threshold-report /results/gnn-v9-validation.metrics.json --output /results/gnn-v9-bootcamp.metrics.json
docker compose -p pix-gnn-validation down --volumes --remove-orphans
```

O segundo avaliador usa o contrato de `examples/pix.json` e históricos fictícios
de pagamento habitual, destinatário novo, liquidação rápida e origem com contatos
de risco. São regressões ilustrativas, não observações adicionais de uma população.

## Limites

Os modelos recebem o mesmo cenário; resultados não são somados como observações
independentes. Pares artificiais e família do gerador induzem dependência. 2FA
solicitado não comprova fraude detectada ou autenticação realizada. A intervenção
é simulada no candidato final sobre histórico congelado; não mede todos os efeitos
de feedback em perfis de uma sequência com contribuição ativa.

[test_gnn_validation.py](../tests/test_gnn_validation.py) verifica propostas,
seleção de corte, denominadores e critérios. O [inventário](testes-politicas.md)
lista os testes da implementação atual.
