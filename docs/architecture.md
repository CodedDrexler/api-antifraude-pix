# Arquitetura da implementação vigente

Política `pix-score-v9`; a versão OpenAPI da aplicação é `1.0.0`.
Fontes: [app.py](../src/app.py), [controller](../src/controllers/pix_controller.py)
e [schema SQL](../database/database.sql).

## Camadas

| Caminho | Responsabilidade |
|---|---|
| `src/app.py` | Rotas e composição de política, banco e serviços opcionais. |
| `src/middlewares/` | Contexto/log, limites de leitura do corpo e headers. |
| `src/schemas/` | Validação e normalização do pedido. |
| `src/resources/` | Fronteira HTTP e projeção do DTO público. |
| `src/controllers/decision_engine.py` | Motor puro, sem SQL: regras, confiança contextual, pontos e decisão inicial. |
| `src/controllers/account_untrust.py` | Incrementos próprios e restrição temporal por conta. |
| `src/entity_risk.py` | Titular, cadastro societário verificado e composição optativa do fator `graph`. |
| `src/gnn/` | Construção do grafo, inferência e contribuição limitada a 2FA. |
| `src/repositories/` | Consultas, travas e inserção. |
| `src/models/` | Mapeamento SQLAlchemy. |
| `src/dtos/` | Auditoria interna e resposta pública. |
| `src/errors/` | Erros de domínio e tradução HTTP. |

Python usa namespace packages, imports `src.` e entrada `src.app:app`.
O registro das regras é explícito em `src/risk/registry.py`.

## Sequência de uma nova análise

1. Middleware limita a leitura do corpo; schema normaliza documento e datas UTC.
2. Controller obtém travas PostgreSQL por ID, documento do pagador e aparelho.
3. Mesmo ID/hash recupera a decisão; conteúdo diferente gera 409.
4. O horário de recepção é capturado depois das travas. O repository consulta o
   histórico disponível, respeitando os cortes de evento e recepção.
5. `DecisionEngine` avalia as 13 regras e a atenuação contextual. Pondera os
   sinais, aplica tetos e decide pelos limites fortes, score e ausência de perfil.
6. `account_untrust` calcula o incremento próprio e pode agravar a decisão.
7. `entity_risk`, se habilitado, agrega o titular e avalia vínculos do cadastro.
8. O grafo temporal roda por último. Em `contribute`, pode mudar somente
   `approved` para `two_factor_required`, com manifesto compatível e score suficiente.
9. Controller salva pedido e evidências juntos, confirma o commit e retorna o resumo.
   A dependency faz rollback de qualquer trabalho restante e fecha a sessão.

`processing_time_ms` termina antes da inserção: inclui travas, consultas e motores,
mas exclui persistência, commit e transporte. GET/replay não executam o motor.

## Persistência e concorrência

`pix_analysis` guarda ID interno, UUID público, ID do chamador, hash SHA-256,
identidades de origem/destino, documento, aparelho, valor, datas, payload JSONB,
status e `decision_metadata`. Não há tabela de cadastro de contas.

As identidades de conta excluem abertura e aparelho, mas incluem instituição
quando informada. O histórico de envio por documento reúne contas do titular;
o acumulado próprio continua por identidade de conta.

Travas de transação usam hashes reduzidos a 64 bits e ordem numérica estável.
O isolamento é READ COMMITTED. As travas por documento e aparelho serializam
tentativas concorrentes também entre processos/réplicas. Há limite de 4s por
espera de trava, 5s por comando SQL e 5s para aguardar conexão do pool.
Esses limites não formam um prazo total para a análise.

Trigger recusa UPDATE/DELETE; restrições SQL limitam status, valores e unicidade.
O administrador do banco pode contornar esses controles. O Compose usa o usuário
administrativo `pix`; o papel restrito preparado na migração 003 não é automático.

O SQL inicial só executa em volume novo. Migrações pendentes devem ser aplicadas
a bases existentes; não se apaga o volume para atualizar o schema. A aplicação não
executa `create_all` nem migrações na inicialização.

## Modos, contrato e operação

API e Compose escolhem GNN `contribute` e entidade `shadow`. A classe de grafo
isolada usa `shadow`; o controller sem serviços explicitamente fornecidos usa
ambos desligados. Treino não ocorre na requisição. A imagem de produção contém
apenas o candidato 42; os comparadores ficam na imagem de testes.

HTTP expõe `key`, `status` e `metadata` com `risk_score`,
`bank_notification_required` e `untrust_score` quando disponível.
`include_details=true` acrescenta somente `rules`. Política, fatores, duplicidade,
tempos e diagnóstico do modelo ficam na auditoria interna.

`/health` e `/health_check` verificam processo; `/ready` consulta a tabela.
O corpo é limitado a 32 KiB e sua leitura a 10s; o processamento posterior não
está incluído nesse prazo. Logs registram método, rota parametrizada, status,
tempo e request ID, sem payload, documento ou IP.

Rotas não exigem token. API publica em loopback; PostgreSQL não publica porta.
Container API usa usuário sem root, filesystem somente leitura e capabilities
removidas. Não há autenticação, liquidação, execução de 2FA, aviso externo,
retenção ou monitoramento institucional. Veja [controles operacionais](banking-review.md).
