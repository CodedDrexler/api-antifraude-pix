# Risco do titular e vínculos societários

Implementação da camada `entity_risk`, API 2.4.0. O modo padrão é **shadow**:
calcula e grava as evidências sem alterar score ou decisão. O GraphSAGE existente
continua disponível; esta camada é uma heurística explicável, sem retreino.

## O que mudou

| Nível | Fonte e significado |
|---|---|
| Conta | `account_untrust`, preservado: incrementos próprios daquela conta, em 24 h |
| Titular | `entity_risk.own_entity`: os mesmos incrementos independentes agregados por CPF ou CNPJ entre contas, sem somar novamente o score relacional |
| Vínculos | `entity_risk.relationships`: exposição a entidades relacionadas por função societária verificada e período de validade |

Uma conta nova não apaga o histórico próprio de seu titular. Um CPF com histórico
próprio zero pode apresentar exposição relacional alta por controlar CNPJs com
ocorrências confirmadas. Os indicadores são distintos: ausência de evidência própria
não comprova confiança e exposição não é confirmação de que o titular cometeu fraude.

Entradas e saídas de Pix também passaram a ter indicadores separados em
`entity_risk.financial_features`: maior untrust, três maiores valores, proporção de
contatos suspeitos e pares de recebimento/repasse em até 30 minutos. São considerados
os últimos dez contatos de cada direção, em 24 h, com deduplicação de IDs. Cada
recebimento suporta no máximo um par de repasse, com valor de 80% a 125% do recebido,
para destino diferente do remetente. Rejeições e eventos futuros ficam fora.

Assim, um contato com risco 90 entre nove contatos com risco zero continua visível
como **máximo 90 e proporção 10%**, sem desaparecer em uma média de 9.
Esses indicadores financeiros são somente observacionais: o banco registra tentativas
aprovadas ou pendentes de 2FA, sem comprovar liquidação. Seu `score_contribution` é zero.

## Cadastro confiável e vínculos

O pedido de Pix permanece igual e não aceita sócios nem rótulos de fraude.
O servidor carrega um JSON fornecido pelo operador. O arquivo é validado na
inicialização, recebe hash SHA-256 e sua versão/hash ficam na decisão salva.
Configuração inválida impede a inicialização; não é ignorada silenciosamente.

- `config/entity-registry.json` começa vazio e não é carregado automaticamente.
- `examples/entity-registry.example.json` é **inteiramente sintético** e demonstra
  um CPF controlador de dez empresas, cada uma com uma ocorrência independente.
- Não há integração implementada com Receita Federal, QSA, DICT ou fornecedores.
  O operador precisa obter e verificar os dados de uma fonte à qual tenha acesso.
- Documentos precisam estar completos e normalizados. CPF mascarado é rejeitado;
  o sistema não tenta resolver identidade por nome ou dígitos parciais.

Cada vínculo tem identificador, documentos, função, verificação, referência,
data de início, fim opcional e data em que ficou conhecido. Pesos da hipótese:
controlador/beneficiário final 1; administrador 0,5; minoritário 0,2; contador 0.
Papéis fracos não servem como ponte entre empresas.

A busca permite três arestas societárias e até 100 entidades. Esses saltos não são
saltos de Pix. Permitem controlador comum e estruturas intermediárias. Grafo
truncado impede inferências relacionais incompletas, preservando evidências próprias
diretas. A cobertura do cadastro é explicitamente limitada a ele.

## Tempo, confirmação e independência

Ocorrências confirmadas possuem `incident_id`, documentos envolvidos, severidade,
data da ocorrência, data de conhecimento, referência, expiração opcional e revogação
opcional. Um episódio com vários CNPJs usa **um único registro com todos os documentos**.
IDs repetidos são rejeitados. Filiais são contadas pela raiz do CNPJ na contagem de
empresas; isso não transforma um episódio em várias evidências.

Fraudes só entram depois de conhecidas e enquanto não expiradas/revogadas.
A associação à empresa onde ocorreu a fraude precisa existir à época e continuar
ativa na avaliação. Assim, quem entrou depois não herda uma ocorrência anterior.
Vínculos encerrados não são utilizados nesta versão; não há inferência automática
de controle histórico ou responsabilidade após a saída.

Para uma **nova empresa**, o vínculo com seu controlador atual identifica o contexto
presente. Esse vínculo pode ser posterior às fraudes de outras empresas controladas
por ele. A nova empresa ganha exposição contextual, sem ganhar ocorrências próprias.
Essa distinção evita que abrir um CNPJ novo apague o contexto do controlador.

O untrust heurístico continua expirando pelo relógio de recebimento do servidor,
em 24 h por padrão. Ocorrências confirmadas não expiram automaticamente nessa janela:
dependem de sua expiração ou revogação explícita. Decisões antigas continuam imutáveis;
uma revogação só muda novas avaliações.

## Contribuição e decisões

Em `contribute`, a exposição usa a maior severidade ponderada, sem média que dilua
evidência forte. Até 20 pontos de corroboração são acrescidos quando há incidentes
fortes independentes adicionais. O resultado é limitado a 100. Untrust indireto
de empresas relacionadas entra como sinal mais fraco: metade do maior untrust
ponderado, sem somar dezenas de suspeitas fracas como se fossem confirmações.

O modelo de grafo ativo é exclusivamente o v2, que observa sem acrescentar pontos.
Ele não compartilha nem consome o teto de contribuição dos vínculos verificados.

O acréscimo transacional é `ceil(exposição × 20 / 100)`. Ele ocupa o fator
`graph`, com **teto de 20**, sem criar artificialmente dois fatores
independentes para satisfazer a condição de rejeição. Os pontos seguem os limiares
existentes do score e podem contribuir para uma rejeição quando combinados com outros
fatores suficientes. O controle relacional direto só propõe 2FA:

- Untrust próprio agregado do titular ≥ 40, com o controle de untrust habilitado;
- Ocorrência confirmada própria com severidade ≥ 60;
- Pelo menos dois incidentes fortes independentes em caminhos de controle
  verificado, com exposição ≥ 60.

Esses limiares e pesos são hipóteses do protótipo, registrados na auditoria, e não
foram calibrados com fraude real. Peso zero do fator `graph` desativa pontos e
escalada por vínculos; o controle próprio agregado segue a configuração de untrust.
Uma exigência de 2FA ou rejeição anterior nunca é relaxada.

O incremento que alimenta o untrust é calculado **antes** desta camada e apenas com
as regras individuais existentes. A consulta lê exclusivamente
`account_untrust.increment`, nunca o score propagado de `entity_risk`.
Isso impede realimentação CPF → empresa → CPF e renovação de evidências por 2FA relacional.

Limites de leitura: 2.000 incrementos e 300 tentativas financeiras por análise.
Truncagem de incrementos produz untrust próprio `null`, com status `truncated`,
em vez de zero. Truncagem financeira suspende seus indicadores. Ocorrências
confirmadas independentes do cadastro continuam disponíveis.

## Exemplo reproduzido

Comparação com uma operação normal que o motor anterior aprovaria:

| Caso sintético | Antes | `contribute` | Explicação |
|---|---|---|---|
| CPF próprio zero, controla dez empresas com dez incidentes | Aprovar, score 0 | 2FA, score 20 | Exposição 100, próprio permanece 0 |
| CNPJ aberto depois das fraudes, mesmo controlador | Aprovar, score 0 | 2FA, score 20 | Contexto atual do controlador |
| Contador das mesmas dez empresas | Aprovar, score 0 | Aprovar, score 0 | Função não prova controle |
| Uma ocorrência envolvendo dez empresas | Aprovar, score 0 | Aprovar, score 18 | Uma evidência; sem corroboração para 2FA direto |
| Nova conta de CPF com 20 + 20 em outras contas | Aprovar, score 0 | 2FA, score 0 | Titular 40; conta nova 0 |
| Sócio entrou depois da fraude | Aprovar, score 0 | Aprovar, score 0 | Vínculo temporal incompatível |

Os **14 cenários** da demonstração incluem também minoritário, administrador,
vínculo encerrado, revogação, informação futura, expiração, cadastro ausente e
50 empresas limpas sem diluir uma ocorrência forte. Shadow preservou score e decisão
em todos os casos. Isso verifica comportamento e controles, não precisão/recall real.

Resultados: [entity-risk-comparison.metrics.json](../models/entity-risk-comparison.metrics.json).
Para reproduzir com o ambiente de desenvolvimento instalado:

```powershell
python -m scripts.demo_entity_risk
```

## Configuração e banco

Na execução com Docker, configure em `.env`:

```dotenv
ENTITY_RISK_MODE=shadow
ENTITY_REGISTRY_PATH=/app/config/entity-registry.json
```

Preencha o cadastro do operador com dados verificados. Para testar o exemplo
sintético, use seu conteúdo em um ambiente de testes separado. Não misture o
exemplo com cadastro real. `ENTITY_RISK_MODE=contribute` habilita a contribuição;
`off` desativa a camada e suas consultas. Reinicie com rebuild após alterar o código;
para alterar só um cadastro montado, recrie/reinicie a API para recarregá-lo.

Em bases existentes, aplique a migração aditiva
[006_entity_history.sql](../database/migrations/006_entity_history.sql) como administrador:

```powershell
Get-Content -Raw database/migrations/006_entity_history.sql | docker compose exec -T db psql -U pix -d pix -v ON_ERROR_STOP=1
```

Ela cria somente índices, sem apagar histórico. Não há novas tabelas obrigatórias.
As evidências, caminhos, cobertura e indicadores financeiros ficam na metadata
imutável salva no banco. O resumo público não inclui `entity_risk`;
`include_details=true` acrescenta somente os nomes das regras aplicadas. Repetir o
mesmo ID usa a avaliação salva, mesmo que o cadastro ou modo tenham mudado.

Os testes novos cobrem a consulta real em PostgreSQL, persistência e replay,
CPF com dez CNPJs, novo CNPJ, sócio posterior à fraude, papéis distintos, filiais,
deduplicação, expiração/revogação, limites de busca, GNN e score sem contagem dupla.
O ambiente principal não foi reiniciado nem recebeu dados sintéticos; a verificação
integrada usa banco e containers temporários isolados.

Verificação final: **365 testes passaram**, sem falhas ou casos ignorados;
lint e formatação passaram nos 62 arquivos Python. Os containers e o banco
temporários foram removidos ao terminar. Para verificar o código atual, execute
a suíte pelos comandos do [README](../README.md).
