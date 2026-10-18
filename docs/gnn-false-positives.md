# Experimento de falsos positivos do GNN

O experimento em [improve_temporal_gnn.py](../scripts/improve_temporal_gnn.py)
treina novamente três redes com históricos legítimos adicionais e compara suas propostas
às três redes originais. O avaliador não altera pesos das regras nem decisões
salvas. Após a comparação, a integração adotou o candidato 42 somente em
observação. Os artefatos ficam separados em
[models/false-positive-v1](../models/false-positive-v1).

## Resultado de 18/10/2026

A comparação com novas sementes e calibração conservadora passou nos critérios
numéricos nos três candidatos. O novo teste contém 600 positivos e 1.200
legítimos fictícios. Destes últimos, 1.064 seriam aprovados pelas regras; esse é
o denominador da fricção adicional do GNN.

| Modelo e corte | Positivos com 2FA adicional / 600 | Legítimos aprováveis com novo desafio / 1.064 |
|---|---:|---:|
| Original, somente score, recalibrado no conjunto ampliado | 36–49 | 0 |
| Novo, somente score, orçamento pontual de 1% | 503–506 | 5–12 |
| Novo, somente score, corte conservador | 496 em cada semente | 0 |
| Novo, score + valor + dois repasses, corte conservador | 250 em cada semente | 0 |

O corte conservador perdeu entre 7 e 10 intervenções positivas em relação ao
orçamento pontual e eliminou seus 5–12 desafios adicionais em legítimos nesse
teste. O ganho de 496/600 corresponde a 82,67%; exigir também valor e dois
repasses reduz para 41,67%. Não houve rejeição adicional e todos os 1.800
cenários receberam score. O limite superior nominal de 95% para 0/1.064 ficou
em aproximadamente 0,36%; zero observado não comprova erro zero em outros dados.

O exemplo comercial original caiu de 99,95 pontos para 0,69, 2,25 e 0,89 nas
sementes 42, 43 e 44. As propostas preservaram sua aprovação. A origem sintética
com remetentes de risco recebeu mais de 99,99 nos três candidatos e teria 2FA.
Esses exemplos foram usados no desenvolvimento e são regressões, não um teste
independente de generalização.

As regras já restringiam 136 dos 1.200 exemplos legítimos: 124 com 2FA e 12 com
rejeição. Eles incluem aparelhos compartilhados e trajetórias que sobem de uma
primeira referência pequena para valores maiores. A taxa incremental do GNN não
conta esses casos como aprovações e não demonstra que a política inteira tenha
zero falsos positivos. Seus pesos heurísticos exigem avaliação própria.

Os resultados completos estão no [relatório conservador](../models/false-positive-v1/conservative/evaluation.metrics.json),
com os [24 cortes congelados](../models/false-positive-v1/conservative/frozen-thresholds.json).
O primeiro teste, com outro conjunto de 1.800 cenários, também foi preservado no
[relatório inicial](../models/false-positive-v1/evaluation.metrics.json): a proposta
somente score teve 502–504 intervenções positivas e 2–5 desafios legítimos;
com os filtros, 252–253 positivos e 2–3 desafios legítimos. A segunda rodada usa
novas sementes para comparar explicitamente os critérios de calibração.

O padrão da API agora é `gnn-false-positive-v1-seed-42`, ainda em `shadow`.
A semente 42 foi mantida por convenção, sem escolher o melhor modelo após o
teste. A auditoria informa corretamente treinamento na política v9; pesos
antigos continuam informando v7. Os relatórios congelados registram
`replace_default_model=false` porque seus avaliadores não modificam configuração;
a adoção posterior é uma alteração explícita da integração, descrita aqui.
Os hashes dos fontes nos relatórios registram a versão usada na medição, anterior
a essa integração. Pesos e limiares permanecem exatamente os medidos.

Na etapa deste experimento, a contribuição ficou desativada. Os candidatos passaram no experimento sintético,
mas compartilham a família do gerador entre treino e teste e não têm confirmação
de fraude ou liquidação. Nenhum corte foi instalado como regra automática de Pix.
Para usar o novo observador, reconstrua a API com `docker compose up --build -d api`.

Posteriormente, por solicitação explícita para combinar as camadas no bootcamp,
a [integração limitada a 2FA](gnn-contribution.md) passou a usar esse corte no
protótipo. Os números acima descrevem a avaliação congelada, anterior à integração.

A integração final passou em **647 testes**, com lint e formatação aprovados.
Uma regressão antiga com IDs fixos passou a usar transação externa descartada;
foi executada duas vezes no mesmo banco para confirmar isolamento e replay.

## Dados e separação

O gerador [false_positive_cases.py](../scripts/false_positive_cases.py) mantém as
11 categorias anteriores e acrescenta sete: pagamento habitual do contrato,
destinatário novo, liquidação comercial rápida, troca legítima de aparelho,
aparelho compartilhado, origem sintética com remetentes de risco e repasse
legítimo com sinais idênticos aos de uma origem marcada como suspeita.

Os valores dos exemplos derivados do contrato variam entre 60% e 180% do valor
base, preservando a primeira referência aprovada abaixo do piso de histórico.
Contas, titulares e dispositivos são remapeados por conjunto. Não há nomes de
cenário, documentos numéricos ou rótulos de intenção como atributos do modelo.

| Conjunto | Cenários por categoria | Total | Uso |
|---|---:|---:|---|
| Treino | 40 | 720 | Ajustar os pesos da rede |
| Validação | 20 | 360 | Escolher a época pela perda BCE |
| Calibração | 50 | 900 | Escolher e congelar os limiares de intervenção |
| Teste | 100 | 1.800 | Comparar os seis modelos sem reajustes |

As faixas de sementes começam em 1.100.000, 1.200.000, 1.300.000 e 1.400.000.
As datas dos candidatos usam janeiro, abril, julho e outubro, respectivamente.
Todos os históricos passam pelo controlador, pelo acumulado próprio e pela
consulta PostgreSQL real de dois saltos. O grafo de treinamento é extraído dessa
consulta, com os mesmos limites usados na inferência. Cada cenário usa uma
transação externa descartada; não se usa o banco principal.

Cada modelo original e candidato recebe seu próprio limiar, selecionado somente
na calibração. Os hashes dos modelos e os cortes ficam em `frozen-thresholds.json`
antes da geração do teste. Não se escolhe uma semente vencedora após observar o
resultado. Separar o ajuste da rede e a escolha do limiar evita reutilizar os
mesmos dados para ambas as finalidades, conforme a
[documentação de limiares do scikit-learn](https://scikit-learn.org/stable/modules/classification_threshold.html).

As duas propostas continuam limitadas a `approved → two_factor_required`: somente
score ou score acompanhado do piso de valor e dois pares de repasses rápidos.
Não acrescentam rejeições, pontos ao score das regras nem suspeita acumulada.
Os critérios numéricos permanecem os da [avaliação anterior](gnn-v9-validation.md):
ganho de pelo menos 5% nos positivos, teto de 1% no limite superior nominal de
95% para novos desafios legítimos, até 5% por categoria e cobertura mínima de 95%.

## Limite de informação

`ambiguous_legitimate_repass` tem exatamente os mesmos pedidos e históricos de
`mule_direct` para a mesma semente, mas assume uma intenção legítima. O par não
é vazamento entre treino e teste: existe dentro de cada conjunto para expor uma
ambiguidade das informações disponíveis. Uma rede determinística deve produzir
o mesmo score nos dois casos. Não existe ajuste de pesos capaz de separar
perfeitamente intenções que não aparecem nos dados.

O relatório apresenta tanto novos desafios em legítimos quanto ganho em
positivos sintéticos. Reduzir todos os scores e perder toda detecção não passa
na validação. Os cinco exemplos originais do bootcamp são regressões de
desenvolvimento e não entram como amostras adicionais da taxa de erro.

As regressões SQL também verificam a linha de base sem GNN: pagamento habitual
e liquidação legítima mantêm score 0, destinatário novo soma 15 e aparelho
substituído soma 20, com aprovação nesses históricos. Aparelho compartilhado
continua somando 30 e exigindo 2FA conforme a política. Esses testes verificam
o comportamento dos pesos existentes; não demonstram que seus valores são ótimos.

## Calibração conservadora

[calibrate_temporal_gnn.py](../scripts/calibrate_temporal_gnn.py) compara dois
critérios usando os mesmos pesos congelados e novas faixas de sementes:
1.500.000 para 900 cenários de calibração e 1.600.000 para 1.800 de teste.
Os critérios são definidos antes de avaliar esse teste; os modelos não são
treinados novamente. Os dois relatórios são preservados, sem escolher um modelo
vencedor depois dos resultados.

`point_budget` maximiza positivos com até 1% de novos desafios legítimos na
calibração. `confidence_budget` maximiza o mesmo objetivo, mas exige que o limite
superior nominal de Wilson de 95% não ultrapasse 1% e que cada categoria legítima
tenha até 5% de novos desafios. Se nem zero erros oferecem amostra suficiente,
o corte desativa a proposta. Casos já restritos pelas regras não diluem nenhuma
dessas taxas.

Os 24 cortes — seis redes, duas propostas e dois critérios — são salvos antes de
gerar o teste. A execução paralela usa processos separados para isolar os
relógios simulados do controlador e mantém a ordem determinística dos cenários.
Uma regressão compara seus resultados com a execução SQL sequencial. Os dados
e os intervalos continuam exploratórios; selecionar um corte com uma margem
nominal não garante uma taxa real de falsos positivos.

Os dados continuam fictícios; sementes novas não representam outra população.
Pares e modelos são dependentes, por isso intervalos binomiais são apenas
diagnósticos exploratórios. Aprovação ou 2FA não comprova liquidação, fraude ou
autenticação concluída. O experimento também muda o recorte do histórico e usa
a política v9 no treinamento; sem uma ablação, a diferença não pode ser atribuída
somente à inclusão de negativos difíceis.

## Reproduzir

Use um projeto Docker descartável e uma pasta de saída nova:

```powershell
docker compose -p bootcamp-gnn-fp up -d --wait db
docker compose -p bootcamp-gnn-fp --profile gnn build gnn-training
docker compose -p bootcamp-gnn-fp --profile gnn run --rm --no-deps -e PIX_TEST_DATABASE_URL=postgresql+psycopg2://pix:pix@db:5432/pix gnn-training python -u -m scripts.improve_temporal_gnn --output-dir models/false-positive-v1-reproduction
docker compose -p bootcamp-gnn-fp --profile gnn run --rm --no-deps -e PIX_TEST_DATABASE_URL=postgresql+psycopg2://pix:pix@db:5432/pix gnn-training python -u -m scripts.calibrate_temporal_gnn --model-dir models/false-positive-v1-reproduction --output-dir models/false-positive-v1-reproduction/conservative
docker compose -p bootcamp-gnn-fp down --volumes --remove-orphans
```

O script recusa sobrescrever um experimento existente. Treinamento e avaliação
não alteram a API em execução. Os testes de cenários e do recorte SQL
estão em [test_gnn_false_positives.py](../tests/test_gnn_false_positives.py).
