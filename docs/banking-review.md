# Controles operacionais implementados

Revisão do código vigente, política `pix-score-v9`, em 18/10/2026.
Este documento descreve o protótipo; não certifica uma operação bancária.

| Área | Implementação verificável |
|---|---|
| Dinheiro | Centavos inteiros positivos até BIGINT; comparação inteira de perfil. |
| Atomicidade | Pedido/decisão na mesma transação; commit antes da resposta de sucesso. |
| Idempotência | ID único, hash normalizado, replay salvo e conflito 409. |
| Concorrência | Travas PostgreSQL por ID, documento pagador e aparelho. |
| Falhas de banco | Rollback e 503; repetir o mesmo ID recupera eventual commit concluído. |
| Auditoria | JSONB com política/evidências e trigger contra UPDATE/DELETE. Não protege contra administrador do banco. |
| Logs | Método, rota parametrizada, status, duração e request ID; sem payload/documento/IP. |
| Headers | `no-store`, `nosniff`, `no-referrer` e `X-Request-ID`. |
| Corpo HTTP | Até 32 KiB reais e 10s para leitura; POST Pix exige JSON. Não há prazo total para processar a decisão. |
| Erros | 400 para entrada inválida, 404 ausente, 409 conflito, 413 tamanho, 415 conteúdo, 408 leitura, 503 banco e 500 genérico. |
| Container API | Sem root; filesystem somente leitura, `/tmp` limitado e capabilities removidas no Compose. |
| Acumulado/GNN | Acumulado próprio expira; bloqueio optativo desligado. GNN limitado a aprovação → 2FA, com manifesto compatível. |

## Credenciais e banco

O Compose cria e usa `pix` com privilégios administrativos. A migração
[003_runtime_role.sql](../database/migrations/003_runtime_role.sql) prepara
`pix_api` com SELECT/INSERT e uso da sequência. Exige `PIX_API_PASSWORD` no
ambiente do psql, verifica privilégios inesperados de papel existente e não
é executada automaticamente. Alterar `DATABASE_URL` é uma etapa operacional
separada. O código versionado não comprova quais migrações um ambiente aplicou.

## Limitações atuais

As rotas não exigem autenticação e não segregam instituições ou tenants. O
integrador é considerado confiável; a API não comprova documento, IP, aparelho,
conta ou data informados. Qualquer chamador com acesso pode consultar um ID.
API publica somente em loopback no Compose; PostgreSQL não publica porta.

Não há TLS gerenciado pelo serviço, limites bancários reais, cadastro externo de
dispositivos, confirmação de fraude/2FA/liquidação nem envio de aviso ao banco.
`bank_notification_required` é um indicador. Aprovação é uma decisão local.

Não há implementação de retenção/descarte, backups/restauração, métricas/alertas,
rate limiting distribuído, alta disponibilidade ou trilha externa contra alteração
administrativa. Os testes verificam propriedades do código e sua integração local;
não comprovam controles institucionais ou eficácia de prevenção a fraude.

Fontes: [middleware](../src/middlewares/request_limits.py),
[erros](../src/errors/handlers.py), [banco](../src/database.py),
[Compose](../docker-compose.yml) e [inventário de testes](testes-politicas.md).
