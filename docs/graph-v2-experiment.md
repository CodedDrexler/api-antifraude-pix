# Experimento do grafo direcionado com tempo

Atualização de 18/10/2026: o v2 agora está
[integrado à API em observação](graph-v2-api.md). As métricas abaixo registram
o experimento offline anterior, na política v7; não são métricas da integração.

Revisão de 17/10/2026, sobre a política `pix-score-v7`. Foi implementada e
treinada uma versão experimental separada do GNN usado pela API. O resultado
melhorou a identificação dos padrões sintéticos avaliados, mas não sustenta
substituir automaticamente o modelo atual.

## O que foi testado

O grafo v2 distingue conta, titular e dispositivo. Possui seis relações:
enviou para, recebeu de, usa aparelho, aparelho usado por, titular possui conta
e conta pertence ao titular. São duas camadas GraphSAGE com agregações separadas
por relação; não é uma implementação de TGN com memória de eventos.

As conexões de pagamento e dispositivo perdem peso com a idade, com meia-vida
experimental de 12 horas. O peso não é cancelado quando há um único vizinho.
Além dos atributos locais, entram informações de entradas e saídas em 24 horas,
atividade recente, titulares distintos por aparelho, suspeita própria independente
e repasses entre 80% e 125% do recebimento em até 30 minutos. Cada recebimento
suporta no máximo um repasse. O risco do destinatário precisa pertencer à saída
efetivamente pareada; um pagamento suspeito sem pareamento não contamina outro.

Os incrementos de suspeita são calculados pelo motor de regras antes do grafo.
Scores propagados, rótulos e decisões finais não viram novos incrementos.
Rejeições podem preservar evidência própria, mas não criam arestas de pagamento.
Tentativas aprovadas ou pendentes são aproximações observacionais: o projeto
continua sem confirmação de liquidação. Vínculos societários não foram incorporados
ao novo modelo; a camada `entity_risk` existente permanece separada.

## Desenho da comparação

Foram usados **440 cenários de treino, 220 de validação e 440 de teste**,
com datas em janeiro, maio e setembro e identidades separadas entre grupos.
São 11 tipos, incluindo vítimas que pagam uma conta suspeita, comerciantes,
repasses legítimos rápidos, contatos antigos e quatro padrões de conta laranja.
Os dois tipos adicionais são pares que mantêm contas, valores e conexões,
alterando o prazo entre receber e enviar: cinco ou 120 minutos.

O objetivo do rótulo é a intenção simulada da **origem como participante de
repasse suspeito**. Não foram misturados os rótulos de fraude transacional do
gerador antigo com esse objetivo. Todas as intenções são artificiais; velocidade
de repasse, sozinha, não determina fraude real.

Comparações:

1. GNN v1 congelado, preservando os pesos atuais; seu objetivo de treino é diferente.
2. Mesma arquitetura v1 retreinada com os novos cenários e rótulos de origem.
3. Modelo tabular, treinado com os atributos v2 dos nós-alvo e da transação,
   sem propagação por conexões.
4. Grafo v2 com direção, titularidade e tempo, treinado com os mesmos dados.

Os três modelos novos foram treinados com **três sementes predefinidas: 42, 43 e
44**, até 100 épocas. A época foi escolhida pela perda de validação; os limiares
foram escolhidos somente na validação, com orçamentos de falsos positivos de
0%, 1% e 5%. Não houve escolha de uma semente vencedora pelo teste.
As nove execuções reutilizam os mesmos 440 candidatos de teste; não são
3.960 exemplos independentes. Os pares compartilham contexto dentro de cada grupo.

Todos os modelos recebem o mesmo histórico sintético fornecido, com até 300
eventos. Esse histórico é mais amplo que a consulta de uma vizinhança usada pela
API atual. A comparação mede esse experimento offline; integrar a nova consulta
à API exigirá verificação própria de cobertura e custo.

## Resultado com orçamento de até 1% na validação

O teste tem **200 origens de risco simulado e 240 legítimas**. A tabela mostra
intervalos entre as três sementes, sem escolher a melhor execução.

| Modelo | Origens de risco sinalizadas | Legítimos sinalizados | Risco que passou a exigir 2FA na política | Legítimos que passaram a exigir 2FA |
|---|---:|---:|---:|---:|
| V1 atual, limiar original 0,80 | 0/200 | 0/240 | 0 | 0 |
| V1 retreinado | 51–126/200 (25,5%–63%) | 0–6/240 | 28–66 | 0–6 |
| Tabular com atributos v2 | 102–160/200 (51%–80%) | 2–3/240 | 42–80 | 2–3 |
| Grafo v2 direcionado e temporal | **146–163/200 (73%–81,5%)** | **0–7/240** | **71–81** | **0–1** |

Sinalizar pelo modelo não equivale a mudar a decisão. O experimento mantém o
teto relacional de +20 pontos: um Pix de score 0 fica abaixo de 30; um Pix de
score 25 pode passar a exigir 2FA. Os 440 candidatos são aprovados pelo baseline
nessa amostra deliberadamente construída para testar essas fronteiras.
Nenhuma versão acrescentou rejeições nessa comparação.

O limite de 1% na validação **não garantiu 1% no teste**. As sementes 42, 43 e 44
do v2 tiveram respectivamente 7, 0 e 1 legítimos sinalizados: 2,92%, 0% e 0,42%.
Com orçamento zero na validação, o v2 sinalizou 146–160 positivos e 0–1 legítimos
no teste. Com orçamento de 5%, sinalizou 171–173 positivos e 19–21 legítimos.
Isso expõe o custo de aumentar a cobertura; não houve ajuste posterior para
esconder os falsos positivos de teste.

## Casos parecidos

Nos pares temporais de teste, o v2 sinalizou 25–40 dos 40 casos de repasse em
cinco minutos e nenhum dos 40 casos de 120 minutos, no orçamento de 1%.
Um teste demonstra que o modelo v1 congelado produz a mesma previsão para um
par desses, enquanto os atributos temporais do v2 distinguem as sequências.

O problema mais difícil permaneceu entre `mule_direct` e
`merchant_fast_settlement`: o gerador oferece padrões observáveis muito
parecidos para intenções opostas. O v2 sinalizou apenas 0–3 das 40 origens
`mule_direct`, e os falsos positivos concentraram-se nos comerciantes com
repasse rápido. Isso exige contexto adicional; apenas aumentar o peso do
grafo agravaria a fricção. Dados observáveis idênticos recebem o mesmo score,
mesmo quando um rótulo externo informa outra intenção.

O modelo tabular já alcançou parte do ganho, chegando a 80% de cobertura em
duas sementes. Portanto, o resultado não demonstra que toda a melhora vem da
arquitetura de grafo. A comparação favorece investigar os novos atributos e
as relações; ainda faltam ablações separadas de tempo, direção e suspeita própria.

## Verificação e artefatos

Os modelos v2 foram exportados em JSON e validados por uma implementação NumPy.
A maior diferença observada contra PyTorch ficou abaixo de **0,000001**.
O carregador valida esquema, objetivo do rótulo, relações, dimensões e números
finitos; o carregador v1 da API rejeita os arquivos v2 como incompatíveis.

Foram acrescentados **29 testes**: direção, titularidade entre contas, limites
temporais, deduplicação, pareamento de repasses, expiração, recebimento futuro,
histórico incompleto, isolamento de rótulos, identidade entre grupos, exportação
e seleção de limiares com notas constantes ou empatadas. A suíte completa
terminou com **427 testes aprovados**, sem casos ignorados. Lint e formatação
passaram nos 70 arquivos Python. O JUnit local está em
`tmp/graph-v2-tests.xml`, ignorado pelo Git.

- [Métricas completas](../models/gnn-directed-temporal-v2.metrics.json).
- Modelos separados: `models/gnn-directed-temporal-v2-seed-42.json`,
  `models/gnn-directed-temporal-v2-seed-43.json` e
  `models/gnn-directed-temporal-v2-seed-44.json`.
- Comparações por candidato: `tmp/gnn-directed-temporal-v2.rows.json`, arquivo
  sintético local ignorado pelo Git, com scores de todas as versões.
- [Construção do grafo](../src/gnn/temporal_graph.py),
  [inferência](../src/gnn/temporal_model.py) e
  [treino e comparação](../scripts/train_temporal_gnn.py).

Para reproduzir com Docker:

```powershell
docker compose --profile gnn build gnn-training
docker compose --profile gnn run --rm gnn-training python -m scripts.train_temporal_gnn
```

A configuração existente monta `models/`, preservando as métricas e os pesos
v2. Para preservar também os resultados individuais de `tmp/`, acrescente
`-v "${PWD}/tmp:/app/tmp"` ao comando `run`, antes de `gnn-training`.
O modelo atual `gnn-synthetic-v1.json` não é sobrescrito.

## Decisão após o experimento

O v2 ficou disponível como experimento offline. A política, o modelo carregado
e as decisões da API continuam iguais. Antes de contribuição automática, o
próximo passo é testar um novo conjunto temporal com resultados confirmados e
contexto dos repasses comerciais, medir a cobertura da consulta real e avaliar
a sequência completa com mudanças de histórico provocadas pelo próprio 2FA.

Os dois grupos já foram inspecionados durante o desenvolvimento. Os cenários
são enriquecidos, têm rótulos artificiais e usam o mesmo gerador nos três
grupos. Não estimam prevalência, probabilidade de fraude, perdas evitadas nem
taxa de falso positivo em produção. Eventos fora de ordem, recebimentos tardios
e descoberta tardia de fraude não foram simulados no benchmark, embora o teste
unitário impeça usar informação recebida no futuro.
