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

Após o [experimento de falsos positivos](gnn-false-positives.md), o observador
padrão passou a usar o candidato retreinado com a política v9. A semente 42 foi
mantida por convenção. Os pesos originais e os relatórios históricos continuam
disponíveis para reprodução, com caminho explícito nos scripts e regressões.
Após a adoção, a [integração de contribuição](gnn-contribution.md) acrescentou
somente aprovação para 2FA no protótipo. O score das regras permanece separado.

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

Um exemplo offline pode fornecer mais relações que essa consulta. No caso
temporal de `scripts/demo_temporal_graph.py`, fixado nos pesos originais, o conjunto completo tem 20 eventos e 21 nós, com saída
96,9626; a consulta real de dois saltos seleciona 14 eventos e 18 nós, com saída
97,3076 para o mesmo candidato. O teste integrado verifica esse recorte e sua
previsão própria, sem exigir igualdade entre grafos diferentes. Ambos preservam
a decisão por regras e a contribuição zero do modelo experimental.

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
`applied_points` indicava a diferença efetiva no score causada pelo modelo; no v2
é sempre zero, inclusive em `contribute`, e foi retirado do contrato público.

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

## Limites da avaliação

O observador padrão foi retreinado com evidências da política v9 e negativos
difíceis, mantendo os pesos originais v7 para reprodução. A auditoria registra
a política de treinamento de cada artefato em `training_evidence_policy`.
A política atual distingue evidências próprias da origem e confiança por
relação; somente valores a partir de R$ 500 exigem 2FA por ausência de perfil,
e o perfil é formado apenas por aprovações. Os números históricos do
[experimento offline](graph-v2-experiment.md) não são uma medição da eficácia
da API integrada nem justificam contribuição automática.

A [avaliação posterior na política v9](gnn-v9-validation.md) usa o controlador e a
consulta PostgreSQL reais, compara propostas limitadas a 2FA e aplica critérios
explícitos de ganho e falsos positivos. Ela não habilita contribuição automaticamente.

O [experimento com negativos difíceis](gnn-false-positives.md) amplia os casos
legítimos e treina candidatos com o mesmo recorte PostgreSQL. Seus pesos são
armazenados separadamente. O candidato 42 foi adotado explicitamente como
observador após a comparação; os avaliadores não promovem modelos automaticamente.

Os testes de integração estão em `test_temporal_live.py` e
`test_temporal_live_db.py`. Cobrem os dois relógios, limites, legado, replay,
consulta real de vizinhança, falhas, e CPF limpo com vínculos empresariais.

O caso completo está em `test_temporal_case.py`, incluindo o recorte PostgreSQL,
a decisão salva e o replay. Execute a suíte e as verificações de qualidade
pelos comandos do [README](../README.md).
