# Calibração vigente e falsos positivos do GNN

O modelo padrão da API é `gnn-false-positive-v1-seed-42`, treinado com evidências
da política v9 e consulta PostgreSQL de dois saltos. O padrão da API é
**`contribute`**: o manifesto permite somente aprovação → 2FA, sem pontos,
com corte **0,750977** (75,0977 na escala pública). Veja a
[composição e os limites](gnn-contribution.md).

## Artefatos que sustentam a integração

| Arquivo/pasta em `models/false-positive-v1/` | Uso atual |
|---|---|
| `gnn-false-positive-v1-seed-42.json` | Peso padrão da API. |
| Pesos das sementes 43/44 | Comparação predefinida das três sementes, sem escolher vencedor pelo teste. |
| `conservative/evaluation.metrics.json` | Avaliação congelada que sustenta o manifesto ativo. |
| `conservative/frozen-thresholds.json` | 24 cortes: seis modelos × duas propostas × dois critérios. |
| `evaluation.metrics.json` e `frozen-thresholds.json` | Registro do treino e da primeira calibração dos mesmos pesos; necessário para verificar hashes e independência da calibração conservadora. |

Os relatórios não alteram a configuração: `enable_contribution=false` e
`replace_default_model=false` registram o comportamento dos avaliadores. O modo
ativo é escolhido em `src/app.py` e `docker-compose.yml`. O manifesto está em
[config/gnn-contribution.json](../config/gnn-contribution.json).

Os comparadores `models/gnn-directed-temporal-v2-seed-*.json` são referências
fixas para os avaliadores e testes, sem carregamento pela imagem de produção.
Os hashes de fontes nos relatórios identificam a revisão medida, não declaram
que todos os fontes atuais tenham os mesmos bytes. Pesos e cortes congelados
permanecem os avaliados; os testes verificam sua integridade.

## Resultado congelado da calibração conservadora

Fonte: [relatório](../models/false-positive-v1/conservative/evaluation.metrics.json).
O teste tem 600 positivos e 1.200 legítimos fictícios; 1.064 legítimos seriam
aprovados pela linha de base. Esse último é o denominador da fricção adicional.

| Modelo/proposta | Positivos com 2FA adicional / 600 | Novos desafios entre legítimos aprováveis / 1.064 |
|---|---:|---:|
| Comparadores, somente score, recalibrados | 36–49 | 0 |
| Candidatos, somente score, orçamento pontual de 1% | 503–506 | 5–12 |
| Candidatos, somente score, corte conservador | 496 em cada semente | 0 |
| Candidatos, score + valor + dois repasses, corte conservador | 250 em cada semente | 0 |

Não houve rejeição adicional; os 1.800 cenários receberam score. Para 0/1.064,
o limite superior nominal de Wilson 95% fica em aproximadamente 0,36%.
Zero observado não implica erro zero em novos dados. A linha de base já restringia
136 legítimos: 124 com 2FA e 12 com rejeição. A fricção incremental não mede a
taxa de erro da política inteira.

O corte instalado é `candidate-42/score_only_2fa/confidence_budget`.
O critério conservador maximiza positivos na calibração exigindo limite superior
nominal de fricção ≤1% e até 5% por categoria legítima. O orçamento pontual
exige apenas taxa observada ≤1%. Os cortes são congelados antes do teste.
Ausência de amostra suficiente pode desativar a proposta.

## Dados e método

O gerador `scripts/false_positive_cases.py` usa 18 categorias, incluindo pagamento
habitual, destinatário novo, liquidação rápida legítima, troca de aparelho,
compartilhamento e origens sintéticas com contatos de risco.

| Conjunto de treino/primeira avaliação | Cenários | Uso |
|---|---:|---|
| Treino | 720 | Ajustar pesos. |
| Validação | 360 | Escolher época por perda BCE. |
| Calibração | 900 | Congelar cortes. |
| Teste | 1.800 | Comparar sem reajuste. |

A calibração conservadora reutiliza pesos, com 900 cenários novos de calibração
e 1.800 de teste, faixas de sementes 1.500.000/1.600.000. Contas e documentos
são separados entre conjuntos. Os históricos usam controlador real, acumulado
próprio e consulta PostgreSQL, com recepção simulada pelo tempo de evento.
Transações externas descartam cada cenário. Não há treino pela API.

`ambiguous_legitimate_repass` e `mule_direct` podem ter pedidos/históricos idênticos
e intenções assumidas opostas. Um modelo determinístico não separa o que não
aparece nos dados. Modelos e cenários pareados não são observações independentes;
intervalos binomiais são diagnósticos exploratórios.

## Reprodução

Use um projeto Docker descartável. As pastas de saída precisam estar vazias;
os scripts recusam sobrescrever o experimento existente.

```powershell
docker compose -p pix-gnn-fp up -d --wait db
docker compose -p pix-gnn-fp --profile gnn build gnn-training
docker compose -p pix-gnn-fp --profile gnn run --rm --no-deps -e PIX_TEST_DATABASE_URL=postgresql+psycopg2://pix:pix@db:5432/pix gnn-training python -u -m scripts.improve_temporal_gnn --output-dir models/reproduction-fp
docker compose -p pix-gnn-fp --profile gnn run --rm --no-deps -e PIX_TEST_DATABASE_URL=postgresql+psycopg2://pix:pix@db:5432/pix gnn-training python -u -m scripts.calibrate_temporal_gnn --model-dir models/reproduction-fp --output-dir models/reproduction-fp/conservative
docker compose -p pix-gnn-fp down --volumes --remove-orphans
```

Esses comandos não alteram o modelo padrão, manifesto ou decisões salvas.
[test_gnn_false_positives.py](../tests/test_gnn_false_positives.py) verifica
geradores, recorte SQL, cortes, hashes, paridade e ambiguidade; os
[testes de contribuição](../tests/test_gnn_contribution.py) verificam a integração.

## Limites da conclusão

Dados são fictícios e usam a mesma família de gerador. Os números são de
propostas sobre linha de base congelada, não de toda uma população com GNN ativa
do início ao fim. Novos pedidos de 2FA podem reduzir aprovações e mudar perfis
futuros. Regressões integradas verificam algumas sequências desse ciclo; não
substituem uma avaliação populacional completa. Não há confirmação de fraude,
autenticação ou liquidação, nem estimativa de eficácia em Pix real.
