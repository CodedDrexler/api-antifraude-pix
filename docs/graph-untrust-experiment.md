# Experimento: suspeita por vizinhança recente de Pix

Análise de 17/10/2026. Política `pix-score-v6`. **Dados exclusivamente sintéticos.**

A proposta encontra sinais que o score individual não encontra nos cenários
construídos, mas contar conexões suspeitas também penaliza remetentes legítimos.
A combinação de vizinhança com repasses repetidos teve o melhor resultado com
baixa fricção neste experimento; sua cobertura foi pequena. O teste não justifica
habilitar contribuição automática na API nem concluir que uma conta é laranja.

## Escopo e comparação

Foram avaliados **3.150 candidatos**, cada um com seu histórico: 1.050 de
validação e 2.100 de teste. Cada candidato foi comparado nas mesmas cinco versões:

| Versão | Comportamento |
|---|---|
| Atual | Regras e `account_untrust`, sem contribuição do GNN; equivale à decisão em shadow |
| Contagem simples | +5 por conta suspeita única, limitado a +20 |
| Vizinhança ponderada | Desconfiança dos contatos normalizada, com redução por recência e distância; até +20 |
| Ponderada + repasse | Mesma pontuação, exigindo pelo menos dois pares de recebimento e saída rápida da origem |
| GNN existente | GraphSAGE já exportado, contribuição optativa original de +20 a partir de 80; sem retreino |

Parâmetros da hipótese, definidos antes da primeira execução: **2 saltos,
10 contatos recentes por conta, janela de 24 horas, meia-vida de 12 horas,
atenuação de 0,5 por salto adicional e vizinho suspeito a partir de 40 de untrust**.
Nenhuma configuração da aplicação foi modificada.

O grafo de contatos é não direcionado; a verificação de repasse usa a direção
receber → enviar. A busca conta cada conta uma vez, exclui a origem de sua própria
vizinhança e deduplica caminhos. O orçamento permite no máximo 111 nós com dois
saltos. Selecionar os últimos dez contatos pode excluir uma conexão suspeita antiga.

No cálculo ponderado, cada salto usa a média ponderada de `untrust / 100`,
zerando a contribuição de contas abaixo de 40 e mantendo esses contatos no
denominador. Pesos de caminho decaem pelo tempo das arestas. Usa-se a maior
exposição entre os saltos, atenuada pela distância e pela idade da conexão mais
recente da origem, multiplicada por 20 e arredondada para cima.

Repasse significa: saída entre 80% e 125% de um recebimento anterior, em até
30 minutos, para conta diferente de quem enviou. Cada recebimento suporta no
máximo um par. São necessários dois pares históricos; o Pix candidato não cria
evidência histórica. Isso é uma aproximação comportamental, não rastreamento dos
mesmos recursos nem prova de fraude.

## Resultado no gerador que já existia

Foram usados 600 casos de validação e **1.200 de teste**, com novas sementes.
O rótulo indica a intenção fraudulenta do cenário original; não é um rótulo
confirmado de conta laranja da origem. Os 430 casos de fraude e 770 legítimos do
teste tiveram as seguintes decisões no motor atual:

| Medida | Atual | Todas as versões com grafo |
|---|---:|---:|
| Fraudes com 2FA ou rejeição | 430/430 | 430/430 |
| Legítimos com 2FA ou rejeição | 439/770 | 439/770 |
| Fraudes rejeitadas | 47/430 | 47/430 |
| Legítimos rejeitados | 41/770 | 41/770 |
| Decisões modificadas em relação ao atual | — | 0 |

O baseline já intervém em todos os positivos desse gerador, deixando pouca
possibilidade de ganho incremental. Isso inclui 2FA, sem comprovar impedimento de
fraude. A fricção em legítimos é elevada nesse conjunto.
A contagem somou score em 122 candidatos; o GNN existente, em 197, mas nenhum
acréscimo cruzou um limiar de decisão. A versão com repasse não contribuiu nesse
gerador, que não foi construído para representar cadeias de recebimento e repasse.

Na comparação de ordenação por score, com limite de 5% de falsos positivos na
validação, todas as versões escolheram limiar 96 e obtiveram o mesmo resultado
no teste: 47 positivos encontrados e 39 falsos positivos, recall de 10,93% e
FPR de 5,06%. O limite selecionado na validação não garante o mesmo FPR no teste.

## Resultado nos casos específicos de conta laranja

Foram acrescentados 450 casos de validação e **900 de teste**: 400 origens
laranja simuladas e 500 legítimas. Os nove cenários têm 100 exemplos cada.
Metade de cada cenário tem score individual 0; metade tem score 25 por
destinatário novo e desconhecido, com valor compatível com o perfil. Essa
construção exercita deliberadamente a fronteira de 30 pontos do 2FA.
Todos os 900 candidatos são aprovados pelo baseline.

| Versão | Laranjas que passaram a exigir 2FA | Legítimos que passaram a exigir 2FA | Rejeições adicionais |
|---|---:|---:|---:|
| Atual | 0/400 | 0/500 | 0 |
| Contagem simples | 150/400 (37,5%) | 100/500 (20%) | 0 |
| Ponderada | 100/400 (25%) | 50/500 (10%) | 0 |
| Ponderada + repasse | 50/400 (12,5%) | 0/500 (0% observado) | 0 |
| GNN existente | 0/400 | 0/500 | 0 |

O GNN carregou e calculou normalmente todos os candidatos. A ausência de
contribuição nessa população é um resultado do modelo e do limiar existentes,
não uma abstenção por falta de histórico. A comparação não representa uma GNN
retreinada para o objetivo de identificar a origem como conta laranja.

A contagem simples acrescentou 2FA para 50 pagadores inocentes que tinham pago
uma conta suspeita e para 50 comerciantes com repasse legítimo rápido. A versão
ponderada eliminou a segunda escalada, mas manteve a primeira. Exigir repasses
repetidos eliminou essas escaladas nos exemplos gerados, ao custo de cobertura:

| Origem simulada | Ponderada + repasse: 2FA adicional |
|---|---:|
| Laranja com contato suspeito direto e repasses repetidos | 0/100 |
| Laranja ligada a suspeito por dois saltos e repasses repetidos | 50/100 |
| Laranja sem vizinho com untrust alto | 0/100 |
| Laranja ainda no primeiro repasse histórico | 0/100 |

O melhor resultado concentrado em dois saltos mostra uma limitação da agregação:
a média da vizinhança direta foi diluída pelos contatos de entrada e de saída.
Portanto, maior proximidade não assegurou maior score nessa fórmula.
Mesmo a versão com repasse elevou o score dos 100 comerciantes com repasse
legítimo; o acréscimo apenas ficou abaixo do limiar de decisão. Alterar pesos ou
limiares pode transformar esse aumento em falsos positivos.

Com limiares de ordenação selecionados somente na validação para orçamentos de
0%, 1% ou 5% de FPR, a versão ponderada com repasse manteve 50/400 positivos e
0/500 falsos positivos no teste, com limiar 30. As outras versões tiveram recall
zero nos limiares que satisfaziam esses orçamentos. Essa comparação usa apenas
o score; não substitui a política com limites fortes e número mínimo de fatores.

## Interpretação e limites

- A hipótese de associação tem utilidade como sinal complementar, mas uma ligação
  isolada não distingue participação na fraude de pagamento legítimo ou vitimização.
- O sinal comportamental reduziu fricção neste conjunto, porém perdeu 350 dos 400
  casos de laranja. Zero falsos positivos observados aqui não garante desempenho real.
- Com teto de +20, uma operação com score 0 continua abaixo do limiar 30. O grafo
  como pequeno acréscimo não resolve sozinho uma conta laranja sem outros sinais.
- Os testes são enriquecidos e têm rótulos artificiais por intenção do gerador.
  Não estimam prevalência real, precisão em produção, prejuízo evitado ou execução
  efetiva do 2FA. Os dois conjuntos têm objetivos de rótulo diferentes e não foram
  misturados em uma única métrica de qualidade.
- O histórico é de **tentativas**. Foram excluídas ligações rejeitadas, mas as
  pendentes de 2FA continuam como aproximação de movimentação. Não há confirmação
  de liquidação nem acesso ao histórico global de todo o Pix.
- Untrust foi recalculado pelas próprias regras individuais, nunca pelos rótulos
  nem por pontos propagados. Ele também pode refletir comportamento legítimo atípico.
- A simulação ordena eventos e usa seu horário como recebimento do servidor. Não
  mede atrasos, eventos fora de ordem, concorrência nem chegada tardia de rótulos.
- O histórico de baseline é congelado entre as versões; só o candidato final é
  alterado. Uma mudança de política em toda a sequência pode alterar decisões,
  familiaridade e perfis futuros, e exige outro replay.
- Os primeiros resultados foram inspecionados durante a correção dos cenários:
  valores abaixo do mínimo não acionavam a fronteira pretendida e um contato
  antigo alterava acidentalmente o perfil do pagador. Foram adicionados testes
  para esse isolamento. Este é um experimento exploratório, não um holdout
  confirmatório intocado.

**Recomendação:** manter a proposta como experimento em shadow, com dois saltos
e limite de contatos. Antes de atribuir pontos na API, validar com pagamentos
liquidados, rótulos confirmados disponíveis à época e contexto cadastral da conta.
Revisar a agregação de entrada/saída e a diluição da média: o resultado atual não
sustenta escolher pesos ou identificar laranjas automaticamente.

## Reprodução e verificação

Script: [evaluate_graph_untrust.py](../scripts/evaluate_graph_untrust.py).
Métricas: [graph-untrust-experiment.metrics.json](../models/graph-untrust-experiment.metrics.json).
O relatório JSON contém parâmetros, contagens por cenário, limiares escolhidos
na validação e hashes dos fontes. Resultados por candidato ficam em
`tmp/graph-untrust-experiment.rows.json`, ignorado pelo Git.

Com a imagem local de testes já disponível, executar na raiz em PowerShell:

```powershell
docker run --rm --network none --mount "type=bind,source=${PWD},target=/app" --workdir /app -e PYTHONDONTWRITEBYTECODE=1 bootcamp-tests:latest python -m scripts.evaluate_graph_untrust
```

Foram aprovados **119 testes** dos arquivos de experimento, GNN, política de
score e auditoria de regras. Lint e formatação dos dois arquivos novos passaram.
O experimento rodou em container sem rede; não alterou a API, o banco, os pesos
treinados ou a política em uso.
