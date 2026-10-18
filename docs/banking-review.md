# Revisão de práticas bancárias

Revisão de código e testes em 17/10/2026. Escopo: API demonstrativa de análise de
risco. Não constitui certificação, homologação Pix, pentest ou auditoria institucional.
O serviço não está pronto para operar como sistema bancário de produção.

## Controles existentes e correções

| Área | Evidência no projeto | Situação |
|---|---|---|
| Dinheiro | Centavos inteiros, limites de tipo e comparação inteira | Adequado ao contrato |
| Atomicidade | Pedido e decisão na mesma transação, commit antes de 200 | Implementado |
| Idempotência | ID único, hash normalizado, conflito 409, replay sem recálculo | Implementado e testado |
| Concorrência | Travas PostgreSQL por ID, pagador e aparelho, em ordem estável | Implementado e testado |
| Falhas do banco | Rollback, timeouts, 503 e repetição com o mesmo ID | Implementado |
| Auditoria das decisões | JSONB com política, evidências, hash do modelo e trigger contra UPDATE/DELETE | Parcial; administrador ainda pode contornar |
| Privacidade em logs | Rotas parametrizadas, sem payload/token/documento/IP | Implementado; não há SIEM |
| Cache e interpretação | `no-store`, `nosniff`, `no-referrer`, inclusive em erros | Corrigido nesta revisão |
| Requisições | Até 32 KiB reais, inclusive envio em blocos, prazo total de 10 s, POST Pix exige JSON | Corrigido; 413/408/415 |
| Falhas inesperadas | Erro genérico com request ID; log sem texto da exceção/SQL | Corrigido e testado |
| Container API | Sem root, filesystem somente leitura, `/tmp` limitado e sem execução, capabilities removidas | Reforçado e testado |
| Risco acumulado | Janela por conta no tempo do servidor, sem autorreforço e com 2FA conservador | Implementado; parâmetros experimentais |

## Pendências prioritárias para produção

**1. Menor privilégio no PostgreSQL.** O Compose local ainda usa `pix`, criado pelo
PostgreSQL como administrador. Esse usuário pode truncar a tabela, alterar o
trigger ou modificar o schema; o histórico não é imutável contra um administrador.
A migração `003_runtime_role.sql` está preparada, mas **não aplicada**: a revisão
automática bloqueou a criação/concessão de acesso sem autorização explícita.
Ela cria `pix_api` com SELECT/INSERT e uso da sequência, sem UPDATE, DELETE,
TRUNCATE, privilégios administrativos ou propriedade da tabela. Também valida
privilégios inesperados em uma identidade pré-existente. A senha vem do ambiente
do psql; nenhuma senha foi gravada na migração. A troca deve ser concluída antes
de considerar o ambiente restrito. Isso não substitui backups nem trilha externa
resistente a alterações pelo administrador.

**2. Identidade e transporte.** A API não exige autenticação por token.
Produção exige TLS com validação, identidade por serviço,
credenciais curtas/rotacionáveis e autorização por escopo; mTLS e OAuth podem
compor essa solução. API key sozinha não é proteção suficiente para dados bancários.
O contrato pressupõe um único integrador confiável: não há segregação por banco,
usuário ou tenant. Qualquer chamador pode consultar qualquer análise e seus detalhes.
Não publicar esse serviço como API multicliente sem autorização por objeto.

**3. Evidências reais de confiança e fraude.** `approved` significa apenas decisão
local do motor. Não confirma liquidação, posse do dispositivo ou sucesso de 2FA.
Desde a v9, pendências de 2FA não formam referência de valores. Sem histórico,
o limite demonstrativo de R$ 500 determina a confirmação adicional por ausência
de referência; os demais controles continuam ativos em qualquer valor.
Produção precisa de eventos confiáveis
de resultado, estados explícitos, deduplicação e reconciliação. O GNN é sintético
e o acumulado é heurístico; nenhum deles está calibrado para risco real.

**4. Tempo e atributos do chamador.** A frequência e o perfil do exercício usam
`transaction_date`, permitindo reproduzir eventos antigos. Um chamador capaz de
forjar datas, documentos, agência/conta ou device_id pode contornar sinais. O
acumulado novo usa horário de recepção do servidor, mas isso não elimina a
necessidade de validar o tempo e os atributos no ingresso da operação real.
É preciso separar ingestão ao vivo de replay/backfill e não confiar no cliente final.
A identidade da origem deve incluir instituição canônica e cadastro autenticado.

**5. Controles bancários do Pix.** Limites efetivos da conta/período, destinatários
cadastrados, cadastro real de dispositivos e informações de segurança do ecossistema
não estão integrados. Desconhecido no histórico local não significa não cadastrado
no banco. O sinal noturno do app não dispensa limites nos outros canais.
`bank_notification.status=indicated_only` é apenas um indicador solicitado para
o protótipo; não representa comunicação entregue ou um processo regulatório.

**6. Disponibilidade e proteção operacional.** Ainda faltam limitação distribuída
de taxa/concorrência, proteção de borda, testes de carga, métricas/alertas, alta
disponibilidade, backups com testes de restauração e objetivos de recuperação.
Pool e timeout por comando não são prazo total da análise. Um controle apenas em
memória por réplica não seria suficiente; por isso não foi apresentado como solução.

**7. Governança e dados pessoais.** Faltam política de retenção e descarte,
criptografia em repouso com gestão de chaves, gestão de acessos e auditoria,
resposta a incidentes, segregação de ambientes, controle de mudanças de política,
análise de dependências e imagens, pentest e validação independente dos modelos.
Payload inclui documentos, IP e eventual geolocalização: coletar e reter apenas
o necessário conforme as obrigações aplicáveis. O identificador de conta em hash
é pseudônimo, não prova de anonimização.

## Base da revisão

A [Resolução CMN 4.893](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=4893&tipo=Resolu%C3%A7%C3%A3o+CMN)
orienta controles de segurança cibernética, rastreabilidade, acessos e continuidade
para instituições no seu âmbito. A [Resolução BCB 85](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=85&tipo=Resolu%C3%A7%C3%A3o+BCB)
é referência para instituições no âmbito específico nela previsto. A aplicação
normativa depende do tipo de instituição e da operação, além do código desta API.

A [IN BCB 491](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=491&tipo=Instru%C3%A7%C3%A3o+Normativa+BCB)
e a [IN BCB 512](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=512&tipo=Instru%C3%A7%C3%A3o+Normativa+BCB)
são referências para cadastro de dispositivos e limites Pix. Os pontos de risco
do exercício não substituem esses controles. As práticas de
[segurança de APIs da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
fundamentam limites de entrada, cache, conteúdo, erros e autorização.

Testes cobrem as propriedades locais; não comprovam controles de infraestrutura
ou processos institucionais ausentes. A documentação distingue o que foi
implementado, o que foi preparado e o que depende de integração/infraestrutura.
