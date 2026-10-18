# Grafo v2 na API

Integração de 18/10/2026, API 2.5.0. O grafo direcionado e temporal passou a
executar em cada **nova análise** de Pix no modo `shadow` por padrão. Seu
resultado fica salvo em `metadata.gnn_v2`, separado do GNN v1 e de `entity_risk`.
O v2 não adiciona pontos, não muda a decisão e não alimenta o acumulado próprio.

## Configuração e execução

```dotenv
GNN_V2_MODE=shadow
GNN_V2_MODEL_PATH=/app/models/gnn-directed-temporal-v2-seed-42.json
```

Os modos disponíveis são `shadow` e `off`. `contribute` é recusado na
inicialização, pois a integração é observacional. O modelo da semente 42 é
um padrão fixo, sem seleção automática do melhor resultado de teste.
O treinamento não ocorre em requisições; a API usa somente NumPy.

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

O resumo da resposta inclui, quando o modelo calculou uma avaliação:

```json
{
  "gnn_v2": {
    "mode": "shadow",
    "status": "scored",
    "gnn_score": 12.3456,
    "applied_points": 0,
    "model_version": "gnn-directed-temporal-v2-seed-42",
    "feature_version": "pix-directed-temporal-v2"
  }
}
```

O número é apenas ilustrativo. O score é a saída não calibrada do modelo,
multiplicada por 100; não é uma probabilidade de fraude.

Com `include_details=true`, ficam disponíveis hash do modelo, limites, cobertura,
cortes dos dois relógios, quantidade de eventos, atributos normalizados da
transação e duração da construção/inferência. A duração total da análise
continua em `metadata.processing_time_ms` e inclui as consultas ao banco.
A política salva também identifica a configuração do v2.

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

## Limites da avaliação

Os pesos continuam sendo os do experimento sintético, treinados sobre evidências
da política v7. A política v8 passou a distinguir evidências próprias da origem
e confiança por relação; isso muda o contexto de entrada e está explicitado
em `training_evidence_policy` e `own_evidence_version`. Os números do
[experimento offline](graph-v2-experiment.md) não são uma medição da eficácia
da API integrada nem justificam contribuição automática.

Os testes de integração estão em `test_temporal_live.py` e
`test_temporal_live_db.py`. Cobrem os dois relógios, limites, legado, replay,
consulta real de vizinhança, falhas, e CPF limpo com vínculos empresariais.

Verificação conjunta de 18/10/2026: **493 testes aprovados**, sem casos ignorados,
incluindo a integração v2, o perfil por relação e a atribuição das evidências
da política v8. Lint e formatação passaram nos 77 arquivos Python. O relatório
local desta execução está em `tmp/graph-v2-live-tests.xml`.
