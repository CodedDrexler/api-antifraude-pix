# Decisões de arquitetura

## Referências e escopo

Base: [CodedDrexler/bootcamp-qi-tech](https://github.com/CodedDrexler/bootcamp-qi-tech),
commit `10465f6af76f571be9928454f9ddfd71c983c2bd`.
O repositório contém um banco demonstrativo e os exemplos do Base Service.
Este projeto aproveita seu desenho de camadas, FastAPI, SQLAlchemy, PostgreSQL,
commit no controller e erros estruturados para o problema Pix.
As funcionalidades bancárias daquela entrega não fazem parte deste serviço.

Materiais lidos:

- `Desafio Antifraude Pix.pdf`, especialmente contrato, escopo e modelo do README.
- `Hackathon Antifraude Pix.pdf`: decisão síncrona, histórico, fricção e justificativa das regras.
- `Bootcamp_QI_Tech_2026_-_Dia_1_Tarde.pdf`: responsabilidades das camadas do Base Service.
- `Bootcamp QI Tech Aula 2.pdf`: contratos, modelagem, isolamento, fluxos e RFC.
- `Bootcamp 4 aula Tarde.pptx`: recapitulação, testes por HTTP, Docker, idempotência e operação.

O desafio do hackathon define o escopo atual. Os materiais anteriores descrevem
uma entrega bancária distinta; cadastro, saldo, porquinhos e interface não entram aqui.
Também não existe integração externa no caminho da decisão.

## Camadas

```text
src/app.py                     registro explícito das rotas e composição
src/middlewares/               request ID e log
src/schemas/                   formato e normalização da entrada
src/resources/                 fronteira HTTP
src/controllers/               fluxo, agregação do score e commit
src/risk/rules/                regras puras separadas por fator de risco
src/risk/types.py              contexto de avaliação e sinais encontrados
src/risk/scoring.py            cálculo compartilhado de pontos, tetos e decisão
src/repositories/              consultas, travas e escrita
src/models/                    mapeamento das tabelas
src/dtos/                      resposta pública
src/errors/                    erros de domínio e tradução para HTTP
database/database.sql          criação e restrições do PostgreSQL
```

O `DecisionEngine` é uma política pura chamada pelo controller. Recebe uma
transação e um resumo do histórico, sem abrir conexões ou conhecer HTTP.
As regras de `activity`, `duplication`, `exposure`, `account`, `counterparty`, `profile`,
`device` e `access_context` ficam em módulos próprios de `src/risk/rules/`.
Cada função recebe um `RuleContext` e produz `RuleMatch` com código, observação,
limiar e indicação de limite forte. O registro explícito em `src/risk/registry.py`
preserva a ordem dos motivos. As regras não consultam o banco nem calculam pontos.
O `DecisionEngine` reúne regras, histórico e evidências da resposta. As funções
de `src/risk/scoring.py` calculam pesos, tetos e faixas de decisão tanto para
as regras quanto para a contribuição opcional do GNN. O tipo `History` fica
em `src/risk/types.py`, sem depender do repository ou de SQLAlchemy.
O GNN continua em `src/gnn/`, com contribuição aplicada depois do score das regras.
O controller obtém o histórico pelo repository e escolhe quando confirmar a escrita.
O resource devolve exclusivamente `key`, `status` e `metadata`.

Os diretórios Python usam namespace packages do Python 3.12, sem `__init__.py`.
O código importa módulos explicitamente; o registro de regras fica em
`src/risk/registry.py`, sem inicialização implícita de pacotes.

A política atual `pix-score-v8` usa contribuições por regra, tetos por grupo,
faixas de score e limites fortes explícitos. A [pesquisa e o cálculo completo](risk-scoring.md)
detalham o racional. O score usa o mesmo retrato de histórico obtido dentro da
transação protegida pelas travas existentes. Análises antigas mantêm seu conteúdo;
novos IDs recebem o score salvo em `decision_metadata`, sem mudança de schema SQL.

Um GraphSAGE experimental adiciona a avaliação
`metadata.gnn`. O padrão shadow preserva a decisão por regras; contribute é uma
opção explícita para testar até 20 pontos adicionais. Treino, inferência, limites
de histórico e resultados sintéticos estão em [gnn-prototype.md](gnn-prototype.md).
O payload e a decisão continuam atômicos; os índices de dispositivo e destino
possuem migração SQL aditiva para bases existentes.

Adaptações em relação à referência:

- Schemas Pydantic, já usados no projeto local, substituem o decorator de JSON Schema.
  O contrato continua em uma camada própria e aparece em `/openapi.json` e `/docs`.
- Uma dependency abre/fecha a sessão explicitamente; o controller dá commit e a
  dependency faz rollback do que restou. A sessão não fica em variável global ou ContextVar.
- Imports usam `src.` para funcionar sem modificar `PYTHONPATH`.
- A entrada única é `src.app:app`. A porta local é 8000.
- Os endpoints Pix do enunciado continuam singulares; não os renomeamos para outra convenção REST.

## Banco primeiro

`pix_analysis` guarda o pedido validado e sua decisão na mesma linha:

| Grupo | Colunas |
|---|---|
| Identidade | `id` interno, `analysis_key` UUID público, `transaction_id` único do chamador |
| Repetição | `payload_hash` SHA-256 do conteúdo normalizado |
| Histórico consultável | documento do pagador, identidade do destino, dispositivo, centavos, data do evento |
| Evidência | payload JSONB, status, metadata com motivos, sinais e parâmetros da política |
| Auditoria | `created_at`, momento em que o serviço analisou o pedido |

Não há tabela de contas: cada pedido contém um retrato das contas fornecido pelo
chamador. Repetir dados no JSON preserva a evidência de cada decisão, sem criar
onboarding fora do escopo. Colunas de consulta evitam varrer JSON para cada regra.
O índice por pagador/data atende as janelas; o índice parcial de aprovados atende o perfil.
Status válidos, centavos positivos, IDs únicos e JSONs do tipo objeto são restrições SQL.
Um trigger impede UPDATE/DELETE de decisões. O código não executa `create_all`:
o SQL versionado é a fonte da criação do schema.

O volume `pix_data` mantém a história ao recriar a API. O SQL inicial executa
somente em um banco novo. Para evoluir um banco com dados, escreva e aplique um
script incremental revisado. Não apague volumes para atualizar uma instalação.

A v5 adiciona `source_account_identity` e um índice por conta/recepção, com
migração aditiva 004. O acumulado lê os incrementos das decisões imutáveis nos
últimos 24 h de `created_at`, sem reinterpretar registros antigos ou somar o
score acumulado anterior. As travas existentes tornam o incremento atômico.
O aviso ao banco é somente um campo na metadata, sem comunicação externa.
Detalhes e evidência de avaliação estão em [account-untrust.md](account-untrust.md).

## Fluxo e concorrência

1. Middleware gera request ID e registra o contexto da requisição.
2. Schema valida tipos, centavos inteiros, datas com fuso, IP e coordenadas.
3. Controller solicita travas de transação PostgreSQL por ID do Pix, documento do pagador e aparelho.
4. Repository busca o ID. Mesmo conteúdo devolve o resultado original; conteúdo diferente gera 409.
5. Repository calcula o histórico por tempo do evento; o motor avalia todas as regras.
6. Repository insere pedido e decisão juntos. Controller faz commit antes da resposta 200.
7. Dependency faz rollback de trabalho incompleto e fecha a sessão em qualquer saída.

As travas usam SHA-256 com redução para 64 bits e ordem numérica fixa. Colisões
podem serializar pagadores independentes, mas não mudam resultados. A trava por
ID também protege a disputa entre dois pagadores usando o mesmo ID. A trava por
documento impede que seis Pix simultâneos leiam o mesmo contador antigo, inclusive
em processos ou réplicas diferentes. A trava por aparelho serializa titulares
diferentes usando o mesmo device_id, protegendo a contagem de compartilhamento.
O isolamento é READ COMMITTED: cada leitura
após obter a trava enxerga os commits anteriores. A API não depende de locks Python.

A transação pode esperar até 4 s por uma trava; cada comando SQL tem timeout de 5 s.
Esses limites não constituem um prazo total da requisição. Em falha de banco,
responde 503 e o chamador deve repetir com o mesmo ID. Se houve commit mas a
resposta se perdeu, a repetição recupera a decisão já gravada.

## Normalização e limites

CPF/CNPJ perde pontuação e datas viram UTC antes do hash. Ordem das chaves JSON
não importa. Campos opcionais omitidos e explicitamente nulos produzem o mesmo
conteúdo normalizado. O payload persistido é essa versão validada/normalizada,
não os bytes originais da requisição.

Documentos aceitam formato de CPF/CNPJ, sem checagem de dígito verificador: os
identificadores sintéticos do contrato continuam válidos. Não há bureau, cadastro
de dispositivos ou confirmação real de 2FA. `two_factor_required` é uma decisão
final desta análise; o cliente executaria a confirmação fora deste escopo.

A referência temporal das regras é `transaction_date`, fornecida pelo chamador
interno. Pedidos históricos são aceitos; um evento posterior não influencia um
evento anterior, e decisões antigas nunca são recalculadas. O sistema pressupõe
um chamador confiável e não comprova a veracidade de documento, conta, IP ou data.
Para uso real, timestamps confiáveis, controle de atraso e resultados de fraude/2FA
seriam necessários antes de calibrar o motor.

Todos os pedidos válidos inéditos contam para velocity e montante, inclusive
reprovados ou com 2FA: representam tentativas. Aprovações formam o perfil de
valores e a familiaridade. Sem aprovações, a primeira tentativa pendente oferece
uma referência provisória de valor; outras pendências não a elevam. O perfil
registra essa origem explicitamente. Sem feedback de
fraude confirmada, esse perfil também pode ser contaminado. Mudanças de conta,
dispositivo e horário precisam ser calibradas com dados rotulados.

## Operação

`/health_check` é liveness sem banco e `/ready` consulta a tabela. `/health` mantém
a resposta anterior. Os logs JSON têm método, rota parametrizada, status, duração
e request ID; não incluem payload, token, documento, IP nem o ID do Pix na URL.
O header `X-Request-ID` permite correlacionar a resposta com o log.

As rotas aceitam requisições sem exigir `INTERNAL-TOKEN`.
O banco não publica porta no
host e a API publica somente em loopback. O container da API roda sem root.
Métricas, rate limiting, TLS, papéis de banco e retenção são evoluções para uma
operação real, não implementações implícitas nesta entrega.
