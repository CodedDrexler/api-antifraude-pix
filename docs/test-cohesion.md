# Coesão dos testes com a decisão

Atualização de 17/10/2026: a revisão de casos parecidos para `pix-score-v7`
partiu de 365 testes e terminou com **398 aprovados, nenhum ignorado**.
São 33 novos casos, incluindo comparação do simulador com PostgreSQL.
Lint e formatação passaram em 64 arquivos Python. As correções e os resultados
atuais estão em [Casos parecidos, decisões diferentes](decision-contrasts.md).
O restante deste documento registra a consolidação anterior, na v6.

Revisão de 17/10/2026 para `pix-score-v6`: **301 testes passaram**, sem falhas,
erros ou casos ignorados. A suíte anterior tinha 333 casos; a redução líquida
foi de 32. Lint e formatação passaram nos 54 arquivos Python.

## Consolidações realizadas

| Sobreposição encontrada | Responsabilidade consolidada |
|---|---|
| Aparelho desconhecido com três aprovações e R$ 500 em `test_pix` e `test_risk_score` | Um cenário HTTP de score verifica decisão, pontos e regra acionada |
| Primeiro Pix com vários valores sem relação com limiares atuais | O cenário HTTP usa o mínimo válido de um centavo; os limiares monetários ficam na matriz de regras |
| Idade da conta repetida como fronteira unitária e em dois exemplos HTTP | Fronteiras ficam na auditoria; integração mantém conta nova combinada com perfil alto e destino novo que já se tornou familiar |
| Quatorze exemplos unitários repetindo os cenários HTTP de score, perfil, acesso e duplicidade | Integração cobre os exemplos completos; testes de fatores verificam contribuições e desempate do teto explicitamente |
| Exclusões noturnas repetidas em `test_access_patterns` e na auditoria | A auditoria verifica as condições; acesso verifica fusos, canal, fronteiras e mudança de configuração |
| Perfil e confiança espalhados entre `test_pix`, acesso e perfil dinâmico | Referência de valores e elegibilidade ficam em `test_dynamic_profile`; acesso mantém dispositivos e hábito noturno |
| Primeiro Pix e histórico insuficiente com peso zero em módulos diferentes | Matriz de prioridade cobre ambos, com e sem limite forte e com GNN |
| Expiração simulada por passar um histórico vazio | O teste PostgreSQL avança o instante de consulta e comprova a retirada do 2FA após expirar o histórico |
| Auxiliares importados de outro arquivo de testes e inicialização de banco repetida | `conftest.py` concentra HTTP, construção de histórico aprovado e conexão isolada |

Foram preservadas verificações em camadas diferentes quando demonstram contratos
distintos: uma fronteira da regra não substitui a consulta histórica, a gravação
da decisão, a proteção contra concorrência ou a recuperação de evidências.

## Critérios de decisão e localização

| Pergunta verificada | Módulo principal |
|---|---|
| Cada uma das 13 regras ativa e deixa de ativar nas condições corretas? | `test_rule_audit.py`: 46 cenários, incluindo as duas alternativas de novidade noturna |
| Limite forte, recusa por score, 2FA obrigatório e aprovação respeitam a prioridade? | `test_scoring_policy.py`: limiares, quantidade de fatores e exceções obrigatórias |
| Pesos, truncagem, tetos e contribuições sustentam o score? | `test_risk_factors.py` |
| O histórico consultado produz e preserva a decisão esperada na API? | `test_risk_score.py` e `test_history_audit.py` |
| Apenas aprovações ou a referência provisória elegível compõem o perfil? | `test_dynamic_profile.py` |
| Dispositivos, horário e hábito usam vínculos e janelas corretos? | `test_access_patterns.py` |
| Acumulado, aviso e bloqueio optativo preservam decisões mais restritivas? | `test_account_untrust.py` e `test_account_untrust_db.py` |
| Identidade, janela e concorrência de possível duplicidade são respeitadas? | `test_duplicate_payment.py` |
| Validação, idempotência, segurança e formato da evidência funcionam? | `test_pix.py`, `test_api_security.py` e `test_metadata.py` |
| O GNN respeita seu modo, seus limites e as salvaguardas da decisão? | `test_gnn.py`, `test_gnn_http.py` e a matriz de prioridade |

Os dados históricos de auditoria agora mantêm ID, valor e data coerentes entre
payload e colunas. Testes de acumulado usam evidências geradas pelo motor em vez
de alterar manualmente score e regras de forma contraditória.

## Verificação de regressões após a redução

Em arquivos descartáveis dentro do container de testes, sete alterações incorretas
foram aplicadas separadamente. **Todas foram detectadas**, com falhas de asserção
e nenhum erro de coleta ou execução:

1. Desativar a rejeição por limite forte.
2. Excluir o ponto exato do limiar de 2FA.
3. Excluir o ponto exato do limiar de recusa.
4. Recusar sem exigir a quantidade mínima de fatores positivos.
5. Permitir que o 2FA inicial substitua uma recusa por limite forte.
6. Remover o teto global de 100.
7. Arredondar 29,6 para 30 em vez de truncar para 29, exigindo 2FA indevidamente.

O JUnit está em `tmp/test-suite-cohesion.xml`; os resultados das alterações
controladas estão em `tmp/decision-mutations.json`. O resumo e os hashes dos
arquivos estão em [antifraud-audit-results.json](antifraud-audit-results.json),
no campo `test_suite_cohesion`. A execução normal pode ser reproduzida com
`.\testar.bat --no-pause`.
