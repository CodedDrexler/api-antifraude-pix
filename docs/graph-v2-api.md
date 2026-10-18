# Modelo Relacional Temporal v2 — experimental

Integração de 18/10/2026. O grafo direcionado e temporal executa em cada
**nova análise** de Pix no modo `contribute` do protótipo por padrão. Seu
resultado fica salvo em `decision_metadata.gnn_v2`, separado de `entity_risk`.
O v2 não adiciona pontos nem alimenta o acumulado próprio. Pode elevar uma
aprovação para 2FA, respeitando os limites da [integração](gnn-contribution.md).
É o único modelo de grafo da API: a implementação, pesos, treino e configuração
do modelo anterior foram retirados. As evidências já salvas permanecem imutáveis.

O modelo é o **Modelo Relacional Temporal v2 — experimental**. A resposta
pública inclui `untrust_score` somente quando há score do grafo disponível.
`gnn_v2`, `gnn_score`, versões e hashes permanecem apenas na evidência interna
salva. GET e reenvio projetam o mesmo resumo a partir da decisão original,
sem executar novamente o modelo nem alterar o registro.

Tecnicamente, é uma GNN simplificada inspirada em GraphSAGE: duas camadas agregam
mensagens dos vizinhos por tipo de relação e aplicam pesos treinados. Treinamento
em PyTorch e inferência em NumPy executam a mesma rede, com verificação de paridade.
Isso caracteriza a arquitetura, não sua eficácia. Os atributos temporais e o
decaimento das arestas são definidos explicitamente; não há memória recorrente
de eventos como em uma TGN. A base é sintética e a saída não é calibrada.
Referência da agregação: [GraphSAGE, Hamilton et al.](https://arxiv.org/abs/1706.02216).

## Configuração e execução

```dotenv
GNN_V2_MODE=contribute
GNN_V2_MODEL_PATH=/app/models/false-positive-v1/gnn-false-positive-v1-seed-42.json
```

Os modos disponíveis são `contribute`, `shadow` e `off`. O padrão do protótipo
pode elevar aprovação para 2FA com score ≥75,0977 e artefatos válidos; nunca
rejeita sozinho nem gera pontos. O modelo da semente 42 é
um padrão fixo, sem seleção automática do melhor resultado de teste.
O treinamento não ocorre em requisições; a API usa somente NumPy.

O candidato 42 é o modelo padrão treinado com a política v9. Os comparadores
fixos em `models/gnn-directed-temporal-v2-seed-*.json` continuam usados nos
avaliadores e nas regressões temporais; não são carregados pela imagem da API.
Sementes 43/44 são usadas na comparação de estabilidade, sem seleção automática.

Depois de atualizar o código:

```powershell
docker compose up --build -d --wait api
```

Em bancos existentes, aplique o índice aditivo da migração 007, preservando os dados:

```powershell
Get-Content -Raw database/migrations/007_temporal_graph.sql | docker compose exec -T db psql -U pix -d pix -v ON_ERROR_STOP=1
```

Os índices de histórico por documento da migração 006 também devem existir.
A base nova já contém ambos. Registros anteriores à integração continuam com
suas evidências originais: consultar ou repetir um ID não roda o modelo novamente.

## Histórico consultado

A consulta começa nos documentos de origem e destino e no dispositivo do Pix.
Executa até duas rodadas de expansão por pagamentos, titulares e dispositivos,
com até 300 tentativas em 30 dias e até 100 documentos descobertos. Inclui
recebimentos e contas do mesmo titular, além de saídas. O resultado descreve
essa vizinhança limitada; não é uma pesquisa de toda a rede Pix.

O exemplo offline `scripts.demo_temporal_graph` usa explicitamente o comparador
fixo 42 e pode fornecer um histórico mais amplo que a consulta real. Grafos
diferentes têm previsões próprias. Esse exemplo não mede o candidato padrão.

A evidência de suspeita própria é consultada separadamente para os documentos
descobertos, com até 300 incrementos na janela de 24 horas do servidor. Usa
somente `sender-evidence-v2`: incrementos legados que poderiam incluir sinais
do destinatário são ignorados, sem alterar as decisões históricas.

Os relógios são explícitos:

- A janela dos pagamentos e o decaimento das conexões usam a data do Pix.
- A disponibilidade das informações e a expiração da suspeita usam o horário
  de recebimento registrado pelo servidor.
- Uma data antiga informada no pedido não descarta evidência própria já
  recebida. A consulta própria independe da data declarada nos eventos.
- O candidato atual não entra como pagamento histórico nem como incremento
  próprio anterior. Seu valor e suas relações atuais são entradas do modelo.

Rejeições não criam conexões de pagamento, mas podem conter incrementos
independentes válidos. Aprovações e pendências de 2FA continuam sendo tentativas;
o projeto não confirma liquidação.

## Resposta e auditoria

O resumo público usa estes campos dentro de `metadata`:

```json
{
  "risk_score": 30,
  "untrust_score": 12.3456,
  "bank_notification_required": false
}
```

O número é ilustrativo. `untrust_score` é a saída não calibrada do grafo de 0 a
100, não uma probabilidade de fraude nem o acumulado da conta. O campo é omitido
quando não existe avaliação disponível, inclusive com o grafo desligado ou sem
histórico suficiente. O modo do grafo fica somente na auditoria interna.

`include_details=true` acrescenta somente `rules`, com nomes legíveis das regras
aplicadas. Não expõe pesos, política, versões, cobertura ou diagnósticos do modelo.
`applied_points` é sempre zero, inclusive em `contribute`, e fica somente
na auditoria interna.

Hash, limites, cobertura, cortes dos relógios, eventos, atributos normalizados e
tempos continuam na auditoria imutável no banco. O tempo total inclui as consultas
antes da gravação e permanece em `decision_metadata.processing_time_ms`.

O modelo registra `insufficient_history` quando há menos de três tentativas
elegíveis. Histórico financeiro, evidência própria ou vizinhança que excedam
os limites produzem abstenção explícita, sem score parcial. Dados legados
incompatíveis também produzem um estado explícito. Modelo ausente ou inválido
fica `unavailable`; erro de inferência fica `inference_failed`. Esses casos
não alteram o resultado dos controles existentes.

Erros de acesso ao banco continuam seguindo o contrato de erro da API;
não são escondidos como uma análise bem-sucedida. `off` e modelo indisponível
não executam a consulta adicional.

## CPF limpo e empresas com ocorrências

O grafo financeiro v2 não deduz sociedade a partir de uma transferência.
A camada `entity_risk` continua responsável pelo cadastro de vínculos verificados,
seus períodos e ocorrências confirmadas. Um CPF pode manter suspeita própria
zero e apresentar exposição por controlar CNPJs com incidentes independentes.
Vínculo de contador não é tratado como controle societário.

Esse cadastro vem do operador em `config/entity-registry.json`, carregado com
`ENTITY_REGISTRY_PATH=/app/config/entity-registry.json`. O arquivo inicial é
vazio; não existe consulta automática à Receita Federal ou QSA. Somente um
cadastro preenchido e configurado permite avaliar esses vínculos reais.
Não são usados nomes parecidos ou transferências para inventar ligações.

Em `ENTITY_RISK_MODE=shadow`, a exposição e a ação proposta ficam registradas.
Em `contribute`, os critérios existentes de `entity_risk` podem exigir 2FA.
Os testes da integração verificam ambos os modos, mantendo o v2 em observação
e o acumulado próprio do CPF em zero.

## Avaliação e verificação

A [calibração vigente](gnn-false-positives.md) usa históricos sintéticos com
consulta PostgreSQL e negativos difíceis. Os cortes são congelados antes do
teste. A auditoria registra `training_evidence_policy` de cada peso; os modelos
comparativos têm política de origem própria, preservada para reprodução.

O [avaliador v9](gnn-v9-validation.md) e o [treinador](graph-v2-experiment.md)
continuam disponíveis. Executá-los não altera modelo, modo ou decisões da API.
Os números congelados de comparação não medem eficácia da API com contribuição
ativa durante toda uma sequência de pagamentos.

`test_temporal_live.py`, `test_temporal_live_db.py`, `test_gnn_http.py`,
`test_temporal_case.py` e `test_gnn_contribution.py` verificam relógios, consultas,
limites, abstenção, hash, contrato, precedência e replay. Consulte o
[inventário atual e os comandos de testes](testes-politicas.md#execução).
