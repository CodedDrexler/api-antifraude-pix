# Entregável 1 — análise individual dos testes e políticas

Inventário do código disponível em **18/10/2026**, política padrão **pix-score-v9**. Foram identificadas **28 suítes, 230 funções de teste e 544 casos após expandir as parametrizações**. As contagens descrevem testes implementados, não execuções aprovadas.

Cada função tem cenário, resultado esperado, nível de execução e política de negócio rastreável. Os códigos R01–R13 identificam regras; P01–P14 identificam políticas transversais, operacionais ou experimentais. A [consolidação completa](politicas-negocio.md) define os parâmetros e o alcance de cada código.

Atualização posterior: a [ampliação para falsos positivos](gnn-false-positives.md)
acrescentou uma suíte de cenários, calibração, integridade dos artefatos e recorte
SQL, além de regressões do observador retreinado. A execução integrada final
passou em **691 casos**, incluindo os [testes de contribuição](gnn-contribution.md),
com lint e formatação. As 544 variações catalogadas
abaixo representam o inventário anterior; o complemento descreve os novos testes.

## Como interpretar

- **Unitário:** exercita motor/serviço com histórico fornecido, podendo usar mocks; não demonstra consulta real ao banco.
- **ASGI local:** exercita transporte e middleware em memória; não equivale a uma transação Pix persistida.
- **PostgreSQL:** exercita SQL, histórico, controlador ou persistência reais, conforme o cenário.
- **HTTP:** chama o serviço; quando usa a fixture `api`, o resumo público também é comparado à auditoria no PostgreSQL.
- **Offline / artefato sintético:** valida exemplos, pesos exportados, relatórios ou propostas; não ativa uma política no endpoint.
- **Parametrizações:** cada linha de variação é um caso individual; decoradores múltiplos são expandidos pelo produto cartesiano. Os argumentos preservam as expressões do código, inclusive os valores esperados quando declarados; o cenário da função explica a expectativa comum. Um teste sem decorador pode conter várias verificações internas; elas são descritas juntas e contam como um caso coletável.

A leitura e a conferência de correspondência deste catálogo são estáticas. Não foi executada a suíte de negócio nesta tarefa de documentação. A fixture `database_engine` pula os testes dependentes quando `PIX_TEST_DATABASE_URL` não está definido; alguns testes HTTP chamam o serviço diretamente e exigem API disponível mesmo sem essa fixture. Use a execução isolada descrita no [README](../README.md#testar).

## Índice por regra e tópico

- [1. Auditoria individual das 13 regras](#suite-01) — `test_rule_audit.py`
- [2. Histórico inicial e piso de valor](#suite-02) — `test_no_history.py`
- [3. Perfil dinâmico de valores](#suite-03) — `test_dynamic_profile.py`
- [4. Possível pagamento duplicado](#suite-04) — `test_duplicate_payment.py`
- [5. Aparelhos, canal e horário](#suite-05) — `test_access_patterns.py`
- [6. Prioridade e limiares de decisão](#suite-06) — `test_scoring_policy.py`
- [7. Ponderação, tetos e configuração](#suite-07) — `test_risk_factors.py`
- [8. Resultados integrados do score](#suite-08) — `test_risk_score.py`
- [9. Confiança por relação e atribuição da evidência](#suite-09) — `test_contextual_trust.py`
- [10. Confiança contextual no PostgreSQL e HTTP](#suite-10) — `test_contextual_trust_db.py`
- [11. Desconfiança acumulada da conta](#suite-11) — `test_account_untrust.py`
- [12. Expiração do acumulado no PostgreSQL](#suite-12) — `test_account_untrust_db.py`
- [13. Contrastes de causa e isolamento da suspeita própria](#suite-13) — `test_untrust_contrasts.py`
- [14. Equivalência entre replay offline e decisões persistidas](#suite-14) — `test_untrust_replay.py`
- [15. Titular, vínculos societários e ocorrências confirmadas](#suite-15) — `test_entity_risk.py`
- [16. Histórico do titular e vínculos persistidos](#suite-16) — `test_entity_risk_db.py`
- [17. Indicadores direcionais de recebimentos e repasses](#suite-17) — `test_financial_features.py`
- [18. Grafo v2 na API: observação, relógios e falhas](#suite-18) — `test_temporal_live.py`
- [19. Recorte temporal real no PostgreSQL](#suite-19) — `test_temporal_live_db.py`
- [20. Contrato HTTP do score temporal](#suite-20) — `test_gnn_http.py`
- [21. Caso demonstrativo temporal reproduzível](#suite-21) — `test_temporal_case.py`
- [22. Modelo temporal offline e integridade do treinamento](#suite-22) — `test_temporal_gnn.py`
- [23. Experimento heurístico de grafo offline](#suite-23) — `test_graph_untrust_experiment.py`
- [24. Propostas experimentais de 2FA e controle de falsos positivos](#suite-24) — `test_gnn_validation.py`
- [25. Contrato HTTP, histórico e concorrência](#suite-25) — `test_pix.py`
- [26. Proteções de transporte e erros](#suite-26) — `test_api_security.py`
- [27. Resposta pública, explicabilidade e auditoria interna](#suite-27) — `test_metadata.py`
- [28. Elegibilidade do histórico e imutabilidade](#suite-28) — `test_history_audit.py`

## Análise por suíte

<a id="suite-01"></a>

### 1. Auditoria individual das 13 regras

Fonte: [test_rule_audit.py](../tests/test_rule_audit.py). **2 funções / 47 casos.**

`BASE_HISTORY` fornece três aprovações de R$ 200 (soma R$ 600), aparelho e destino conhecidos, quatro tentativas registradas e nenhuma atividade recente. O Pix padrão desta matriz é R$ 500. `NO_REFERENCE` zera aprovações e perfil e torna aparelho/destino desconhecidos. Os argumentos de cada caso são alterações sobre essa base.

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_rule_audit--test_each_rule_activation_boundary_and_exclusions"></a>[`test_each_rule_activation_boundary_and_exclusions`](../tests/test_rule_audit.py#L229) | Unitário | Executa cada cenário de RULE_CASES; confere ativação/ausência, peso, fator, observação e limiar; limites fortes precisam rejeitar com origem hard_limit. As 46 variações estão discriminadas abaixo por regra. | [P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_rule_audit--test_every_configured_rule_has_positive_and_negative_audit_cases"></a>[`test_every_configured_rule_has_positive_and_negative_audit_cases`](../tests/test_rule_audit.py#L247) | Unitário | Compara os códigos configurados com os casos ativos e inativos; todas as 13 regras precisam ter ao menos um exemplo positivo e um negativo. É uma verificação da cobertura do catálogo, não da eficácia antifraude. | [P04 — Configuração do operador](politicas-negocio.md#p04) |

**Casos individuais de `test_each_rule_activation_boundary_and_exclusions` (46)**

Todos verificam o cenário e as políticas da [análise da função](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso / identificação | Cenário individual e resultado esperado | Argumentos | Política |
|---|---|---|---|
| 1 — `velocity_above_limit-below-five-prior-attempts` | Quatro tentativas anteriores ficam abaixo do limite de frequência. **Não aciona esta regra; os demais controles ainda decidem.** | `code='velocity_above_limit'; active=False; history={'recent_count': 4}; changes={}` | [R01](politicas-negocio.md#r01)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 2 — `velocity_above_limit-at-five-prior-attempts` | Cinco tentativas anteriores tornam o Pix atual a sexta tentativa. **Aciona a regra. Rejeita por limite forte.** | `code='velocity_above_limit'; active=True; history={'recent_count': 5}; changes={}` | [R01](politicas-negocio.md#r01)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 3 — `velocity_above_limit-above-five-prior-attempts` | Seis tentativas anteriores também excedem a frequência permitida. **Aciona a regra. Rejeita por limite forte.** | `code='velocity_above_limit'; active=True; history={'recent_count': 6}; changes={}` | [R01](politicas-negocio.md#r01)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 4 — `accumulated_amount_above_limit-one-cent-below-total-limit` | Acumulado com o Pix atual fica em R$ 29.999,99. **Não aciona esta regra; os demais controles ainda decidem.** | `code='accumulated_amount_above_limit'; active=False; history={'recent_amount': 2949999}; changes={}` | [R02](politicas-negocio.md#r02)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 5 — `accumulated_amount_above_limit-at-total-limit` | Acumulado com o Pix atual atinge exatamente R$ 30 mil. **Aciona a regra. Rejeita por limite forte.** | `code='accumulated_amount_above_limit'; active=True; history={'recent_amount': 2950000}; changes={}` | [R02](politicas-negocio.md#r02)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 6 — `accumulated_amount_above_limit-one-cent-above-total-limit` | Acumulado com o Pix atual chega a R$ 30.000,01. **Aciona a regra. Rejeita por limite forte.** | `code='accumulated_amount_above_limit'; active=True; history={'recent_amount': 2950001}; changes={}` | [R02](politicas-negocio.md#r02)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 7 — `first_transaction-no-registered-attempts` | Sem tentativas nem referência aprovada, analisa primeiro Pix de R$ 500. **Aciona a regra.** | `code='first_transaction'; active=True; history={**NO_REFERENCE, 'registered_count': 0}; changes={}` | [R03](politicas-negocio.md#r03)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 8 — `first_transaction-previous-attempt-exists` | Há tentativa anterior; a ausência de referência deve usar a outra regra. **Não aciona esta regra; os demais controles ainda decidem.** | `code='first_transaction'; active=False; history={**NO_REFERENCE, 'registered_count': 1}; changes={}` | [R03](politicas-negocio.md#r03)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 9 — `insufficient_amount_history-attempt-without-eligible-reference` | Há tentativa registrada, mas nenhuma aprovação para referência. **Aciona a regra.** | `code='insufficient_amount_history'; active=True; history={**NO_REFERENCE, 'registered_count': 1}; changes={}` | [R04](politicas-negocio.md#r04)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 10 — `insufficient_amount_history-first-pix-has-own-rule` | Sem tentativa anterior, deve prevalecer a identificação de primeiro Pix. **Não aciona esta regra; os demais controles ainda decidem.** | `code='insufficient_amount_history'; active=False; history={**NO_REFERENCE, 'registered_count': 0}; changes={}` | [R04](politicas-negocio.md#r04)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 11 — `insufficient_amount_history-eligible-reference-exists` | Existe referência aprovada; não se aplica insuficiência de histórico. **Não aciona esta regra; os demais controles ainda decidem.** | `code='insufficient_amount_history'; active=False; history={}; changes={}` | [R04](politicas-negocio.md#r04)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 12 — `new_source_account-one-second-before-seven-days` | Origem tem sete dias menos um segundo. **Aciona a regra.** | `code='new_source_account'; active=True; history={}; changes={'source_age_seconds': 604799}` | [R05](politicas-negocio.md#r05)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 13 — `new_source_account-exactly-seven-days` | Origem atinge exatamente sete dias, fora da faixa de conta recente. **Não aciona esta regra; os demais controles ainda decidem.** | `code='new_source_account'; active=False; history={}; changes={'source_age_seconds': 604800}` | [R05](politicas-negocio.md#r05)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 14 — `new_source_account-one-second-after-seven-days` | Origem tem sete dias e um segundo. **Não aciona esta regra; os demais controles ainda decidem.** | `code='new_source_account'; active=False; history={}; changes={'source_age_seconds': 604801}` | [R05](politicas-negocio.md#r05)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 15 — `new_destination_account-unknown-young-destination` | Destino desconhecido tem sete dias menos um segundo; valor R$ 500. **Aciona a regra.** | `code='new_destination_account'; active=True; history={'known_destination': False}; changes={'destination_age_seconds': 604799}` | [R06](politicas-negocio.md#r06)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 16 — `new_destination_account-destination-exactly-seven-days` | Destino desconhecido atinge sete dias; deixa de ser recente. **Não aciona esta regra; os demais controles ainda decidem.** | `code='new_destination_account'; active=False; history={'known_destination': False}; changes={'destination_age_seconds': 604800}` | [R06](politicas-negocio.md#r06)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 17 — `new_destination_account-below-minimum-value` | Valor R$ 499,99 fica um centavo abaixo do piso desta regra. **Não aciona esta regra; os demais controles ainda decidem.** | `code='new_destination_account'; active=False; history={'known_destination': False}; changes={'destination_age_seconds': 1, 'amount': 49999}` | [R06](politicas-negocio.md#r06)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 18 — `new_destination_account-destination-already-known` | Destino jovem já foi aprovado e é conhecido. **Não aciona esta regra; os demais controles ainda decidem.** | `code='new_destination_account'; active=False; history={}; changes={'destination_age_seconds': 1}` | [R06](politicas-negocio.md#r06)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 19 — `unfamiliar_destination-unknown-with-three-approvals` | Há três aprovações; o destino/aparelho em análise é desconhecido. **Aciona a regra.** | `code='unfamiliar_destination'; active=True; history={'known_destination': False}; changes={}` | [R07](politicas-negocio.md#r07)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 20 — `unfamiliar_destination-fewer-than-three-approvals` | Duas aprovações são insuficientes para aplicar este sinal de novidade/hábito. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_destination'; active=False; history={'known_destination': False, 'approved_count': 2}; changes={}` | [R07](politicas-negocio.md#r07)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 21 — `unfamiliar_destination-below-minimum-value` | Valor R$ 499,99 fica um centavo abaixo do piso desta regra. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_destination'; active=False; history={'known_destination': False}; changes={'amount': 49999}` | [R07](politicas-negocio.md#r07)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 22 — `unfamiliar_destination-destination-known` | Destino conhecido não recebe sinal de desconhecimento. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_destination'; active=False; history={}; changes={}` | [R07](politicas-negocio.md#r07)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 23 — `amount_above_customer_profile-one-cent-below-five-times-average` | Valor R$ 999,99 fica abaixo de cinco vezes a média de R$ 200. **Não aciona esta regra; os demais controles ainda decidem.** | `code='amount_above_customer_profile'; active=False; history={}; changes={'amount': 99999}` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 24 — `amount_above_customer_profile-exactly-five-times-average` | Valor R$ 1.000 atinge cinco vezes a média. **Aciona a regra.** | `code='amount_above_customer_profile'; active=True; history={}; changes={'amount': 100000}` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 25 — `amount_above_customer_profile-one-cent-above-five-times-average` | Valor R$ 1.000,01 excede cinco vezes a média. **Aciona a regra.** | `code='amount_above_customer_profile'; active=True; history={}; changes={'amount': 100001}` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 26 — `amount_above_customer_profile-no-eligible-value-reference` | Sem aprovação de referência, não se calcula desvio de perfil. **Não aciona esta regra; os demais controles ainda decidem.** | `code='amount_above_customer_profile'; active=False; history={**NO_REFERENCE, 'registered_count': 1}; changes={'amount': 100000}` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 27 — `unfamiliar_device-unknown-with-three-approvals` | Há três aprovações; o destino/aparelho em análise é desconhecido. **Aciona a regra.** | `code='unfamiliar_device'; active=True; history={'known_device': False}; changes={}` | [R09](politicas-negocio.md#r09)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 28 — `unfamiliar_device-fewer-than-three-approvals` | Duas aprovações são insuficientes para aplicar este sinal de novidade/hábito. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_device'; active=False; history={'known_device': False, 'approved_count': 2}; changes={}` | [R09](politicas-negocio.md#r09)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 29 — `unfamiliar_device-below-minimum-value` | Valor R$ 499,99 fica um centavo abaixo do piso desta regra. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_device'; active=False; history={'known_device': False}; changes={'amount': 49999}` | [R09](politicas-negocio.md#r09)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 30 — `unfamiliar_device-device-known` | Aparelho conhecido não recebe sinal de desconhecimento. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unfamiliar_device'; active=False; history={}; changes={}` | [R09](politicas-negocio.md#r09)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 31 — `shared_device-two-owners-including-current` | Um titular anterior mais o atual totalizam duas pessoas. **Não aciona esta regra; os demais controles ainda decidem.** | `code='shared_device'; active=False; history={'device_other_owners': 1}; changes={}` | [R10](politicas-negocio.md#r10)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 32 — `shared_device-three-owners-including-current` | Dois titulares anteriores mais o atual totalizam três pessoas. **Aciona a regra.** | `code='shared_device'; active=True; history={'device_other_owners': 2}; changes={}` | [R10](politicas-negocio.md#r10)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 33 — `shared_device-four-owners-including-current` | Três titulares anteriores mais o atual totalizam quatro pessoas. **Aciona a regra.** | `code='shared_device'; active=True; history={'device_other_owners': 3}; changes={}` | [R10](politicas-negocio.md#r10)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 34 — `multiple_devices-two-devices-including-current` | Um aparelho anterior mais o atual desconhecido totalizam dois. **Não aciona esta regra; os demais controles ainda decidem.** | `code='multiple_devices'; active=False; history={'known_device': False, 'payer_other_devices': 1}; changes={}` | [R11](politicas-negocio.md#r11)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 35 — `multiple_devices-three-devices-including-current` | Dois aparelhos anteriores mais o atual desconhecido totalizam três. **Aciona a regra.** | `code='multiple_devices'; active=True; history={'known_device': False, 'payer_other_devices': 2}; changes={}` | [R11](politicas-negocio.md#r11)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 36 — `multiple_devices-known-device-excluded` | Mesmo com três aparelhos, o atual conhecido é excluído da regra de troca. **Não aciona esta regra; os demais controles ainda decidem.** | `code='multiple_devices'; active=False; history={'payer_other_devices': 2}; changes={}` | [R11](politicas-negocio.md#r11)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 37 — `unusual_night_app-night-app-and-new-device` | App noturno sem hábito, com três aprovações e aparelho novo, a R$ 500. **Aciona a regra.** | `code='unusual_night_app'; active=True; history={'known_device': False}; changes={'night': True}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 38 — `unusual_night_app-night-app-and-new-destination` | App noturno com destino novo satisfaz a novidade mesmo com aparelho conhecido. **Aciona a regra.** | `code='unusual_night_app'; active=True; history={'known_destination': False}; changes={'night': True}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 39 — `unusual_night_app-daytime-excluded` | Horário diurno exclui o sinal noturno, apesar de aparelho desconhecido. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={'known_device': False}; changes={}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 40 — `unusual_night_app-habitual-night-use-excluded` | Uma aprovação noturna anterior demonstra hábito e exclui o sinal. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={'known_device': False, 'approved_night_count': 1}; changes={'night': True}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 41 — `unusual_night_app-fewer-than-three-approvals` | Duas aprovações são insuficientes para aplicar este sinal de novidade/hábito. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={'known_device': False, 'approved_count': 2}; changes={'night': True}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 42 — `unusual_night_app-below-minimum-value` | Valor R$ 499,99 fica um centavo abaixo do piso desta regra. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={'known_device': False}; changes={'night': True, 'amount': 49999}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 43 — `unusual_night_app-internet-banking-excluded` | Canal internet_banking à noite não recebe o sinal específico de app. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={'known_device': False}; changes={'night': True, 'channel': 'internet_banking'}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 44 — `unusual_night_app-no-novelty-excluded` | Aparelho e destino conhecidos eliminam a condição de novidade. **Não aciona esta regra; os demais controles ainda decidem.** | `code='unusual_night_app'; active=False; history={}; changes={'night': True}` | [R12](politicas-negocio.md#r12)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 45 — `possible_duplicate_payment-previous-payment-at-window-boundary` | Histórico fornecido informa possível pagamento anterior há exatos 120s; a consulta da janela é validada na suíte de duplicidade. **Aciona a regra.** | `code='possible_duplicate_payment'; active=True; history={'duplicate_transaction_id': 'prior-pix', 'duplicate_elapsed_seconds': 120}; changes={}` | [R13](politicas-negocio.md#r13)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |
| 46 — `possible_duplicate_payment-no-previous-eligible-payment` | Histórico fornecido não contém pagamento anterior elegível. **Não aciona esta regra; os demais controles ainda decidem.** | `code='possible_duplicate_payment'; active=False; history={}; changes={}` | [R13](politicas-negocio.md#r13)<br>[P01](politicas-negocio.md#p01)<br>[P02](politicas-negocio.md#p02) |

<a id="suite-02"></a>

### 2. Histórico inicial e piso de valor

Fonte: [test_no_history.py](../tests/test_no_history.py). **7 funções / 28 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_no_history--test_no_history_amount_floor"></a>[`test_no_history_amount_floor`](../tests/test_no_history.py#L19) | Unitário | Cruza 0/2 tentativas anteriores com 1, 1.000, 49.999, 50.000, 50.001 e 150.000 centavos: abaixo de R$ 500 aprova sem outros sinais; a partir do piso pede 2FA e registra a regra inicial ou de referência insuficiente. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R04 — Referência insuficiente](politicas-negocio.md#r04) |
| <a id="test_no_history--test_no_history_amount_floor_is_configurable"></a>[`test_no_history_amount_floor_is_configurable`](../tests/test_no_history.py#L38) | Unitário | Com piso alterado para 25.000 centavos, 24.999 aprova e 25.000 exige 2FA; o limiar usado fica na política salva. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_no_history--test_no_history_amount_floor_requires_positive_integer_cents"></a>[`test_no_history_amount_floor_requires_positive_integer_cents`](../tests/test_no_history.py#L49) | Unitário | Rejeita piso zero, negativo, booleano, fracionário, string ou nulo; a configuração deve expressar centavos inteiros positivos. | [P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_no_history--test_low_value_without_history_still_respects_other_controls"></a>[`test_low_value_without_history_still_respects_other_controls`](../tests/test_no_history.py#L62) | Unitário | Pix de R$ 10 sem perfil mantém 2FA por aparelho compartilhado e rejeição por frequência ou montante; a dispensa por baixo valor vale só para ausência de referência. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[R01 — Frequência](politicas-negocio.md#r01)<br>[R02 — Montante](politicas-negocio.md#r02)<br>[R10 — Aparelho compartilhado](politicas-negocio.md#r10) |
| <a id="test_no_history--test_first_pix_http_boundary_and_replay"></a>[`test_first_pix_http_boundary_and_replay`](../tests/test_no_history.py#L75) | HTTP + PostgreSQL | Pela API, R$ 10 e R$ 499,99 aprovam, R$ 500 exige 2FA; POST repetido e GET preservam a decisão v9 e a referência indisponível. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_no_history--test_pending_attempt_cannot_raise_the_reference_for_a_small_pix"></a>[`test_pending_attempt_cannot_raise_the_reference_for_a_small_pix`](../tests/test_no_history.py#L85) | HTTP + PostgreSQL | Uma pendência de R$ 1.500 não cria perfil; o Pix seguinte de R$ 10 aprova e só sua aprovação passa a formar referência para avaliar R$ 50. | [R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_no_history--test_policy_change_does_not_recompute_a_saved_first_pix"></a>[`test_policy_change_does_not_recompute_a_saved_first_pix`](../tests/test_no_history.py#L101) | PostgreSQL + controlador/repositório | Salva uma exigência inicial pela v8 e consulta/reenvia com v9; resultado e versão originais permanecem. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

**Casos individuais de `test_no_history_amount_floor` (12)**

Todos verificam o cenário e as políticas da [análise da função](#test_no_history--test_no_history_amount_floor). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `amount=1; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 2 | — | `amount=1; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 3 | — | `amount=1000; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 4 | — | `amount=1000; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 5 | — | `amount=49999; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 6 | — | `amount=49999; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 7 | — | `amount=50000; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 8 | — | `amount=50000; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 9 | — | `amount=50001; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 10 | — | `amount=50001; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 11 | — | `amount=150000; registered=0` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |
| 12 | — | `amount=150000; registered=2` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04) |

**Casos individuais de `test_no_history_amount_floor_is_configurable` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_no_history--test_no_history_amount_floor_is_configurable). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `amount=24999; expected='approved'` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[P04](politicas-negocio.md#p04) |
| 2 | — | `amount=25000; expected='two_factor_required'` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_no_history_amount_floor_requires_positive_integer_cents` (6)**

Todos verificam o cenário e as políticas da [análise da função](#test_no_history--test_no_history_amount_floor_requires_positive_integer_cents). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `value=0` | [P04](politicas-negocio.md#p04) |
| 2 | — | `value=-1` | [P04](politicas-negocio.md#p04) |
| 3 | — | `value=True` | [P04](politicas-negocio.md#p04) |
| 4 | — | `value=500.5` | [P04](politicas-negocio.md#p04) |
| 5 | — | `value='50000'` | [P04](politicas-negocio.md#p04) |
| 6 | — | `value=None` | [P04](politicas-negocio.md#p04) |

**Casos individuais de `test_low_value_without_history_still_respects_other_controls` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_no_history--test_low_value_without_history_still_respects_other_controls). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `history=History(0, 0, 0, False, False, device_other_owners=2); expected='two_factor_required'; reason='shared_device'` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |
| 2 | — | `history=History(5, 5000, 0, False, False); expected='rejected'; reason='velocity_above_limit'` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |
| 3 | — | `history=History(1, 2999000, 0, False, False); expected='rejected'; reason='accumulated_amount_above_limit'` | [R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |

**Casos individuais de `test_first_pix_http_boundary_and_replay` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_no_history--test_first_pix_http_boundary_and_replay). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `amount=1000; expected='approved'` | [R03](politicas-negocio.md#r03)<br>[P11](politicas-negocio.md#p11) |
| 2 | — | `amount=49999; expected='approved'` | [R03](politicas-negocio.md#r03)<br>[P11](politicas-negocio.md#p11) |
| 3 | — | `amount=50000; expected='two_factor_required'` | [R03](politicas-negocio.md#r03)<br>[P11](politicas-negocio.md#p11) |

<a id="suite-03"></a>

### 3. Perfil dinâmico de valores

Fonte: [test_dynamic_profile.py](../tests/test_dynamic_profile.py). **7 funções / 18 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_dynamic_profile--test_reference_average_is_independent_of_available_sample_count"></a>[`test_reference_average_is_independent_of_available_sample_count`](../tests/test_dynamic_profile.py#L16) | Unitário | Com 1, 3 ou 10 aprovações de 1.000 centavos, 5.000 centavos aciona perfil com score 80 e exige apenas 2FA; a média não depende do tamanho máximo da amostra. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_dynamic_profile--test_fractional_average_is_compared_exactly_and_policy_is_configurable"></a>[`test_fractional_average_is_compared_exactly_and_policy_is_configurable`](../tests/test_dynamic_profile.py#L29) | Unitário | Com soma 667, duas amostras e multiplicador 3, 1.000 centavos não aciona e 1.001 aciona; compara inteiros sem erro de arredondamento. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_dynamic_profile--test_invalid_dynamic_profile_configuration"></a>[`test_invalid_dynamic_profile_configuration`](../tests/test_dynamic_profile.py#L40) | Unitário | Cruza tamanho/multiplicador com zero, negativo, booleano, fração e string; ambos exigem inteiro positivo. | [P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_dynamic_profile--test_repository_uses_last_ten_approved_pix_without_day_cutoff"></a>[`test_repository_uses_last_ten_approved_pix_without_day_cutoff`](../tests/test_dynamic_profile.py#L45) | HTTP + PostgreSQL | Seleciona dez aprovações mais recentes, mesmo antigas; remove a aprovação mais velha e ignora pendência, outro pagador e evento futuro. R$ 50 resulta em score 80/2FA. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_dynamic_profile--test_pending_two_factor_pix_cannot_bootstrap_amount_history"></a>[`test_pending_two_factor_pix_cannot_bootstrap_amount_history`](../tests/test_dynamic_profile.py#L81) | HTTP + PostgreSQL | Dois Pix ≥ R$ 500 pendentes continuam sem referência; a segunda tentativa aciona insufficient_amount_history, não aprende o valor da primeira. | [R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_dynamic_profile--test_rejected_and_pending_attempts_do_not_inflate_approved_profile"></a>[`test_rejected_and_pending_attempts_do_not_inflate_approved_profile`](../tests/test_dynamic_profile.py#L96) | HTTP + PostgreSQL | Mantém duas aprovações de R$ 10 apesar de tentativas altas pendentes/rejeitadas; o limite continua R$ 50. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_dynamic_profile--test_old_pending_attempts_never_establish_value_or_familiarity"></a>[`test_old_pending_attempts_never_establish_value_or_familiarity`](../tests/test_dynamic_profile.py#L113) | HTTP + PostgreSQL | Pendências com 31/32 dias aparecem no total registrado, mas não geram perfil, limite, aprovação, aparelho ou destino conhecidos. | [R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |

**Casos individuais de `test_reference_average_is_independent_of_available_sample_count` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_dynamic_profile--test_reference_average_is_independent_of_available_sample_count). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | one-sample | `count=1` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01) |
| 2 | three-samples | `count=3` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01) |
| 3 | ten-samples | `count=10` | [R08](politicas-negocio.md#r08)<br>[P01](politicas-negocio.md#p01) |

**Casos individuais de `test_invalid_dynamic_profile_configuration` (10)**

Todos verificam o cenário e as políticas da [análise da função](#test_dynamic_profile--test_invalid_dynamic_profile_configuration). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `value=0; field='profile_history_size'` | [P04](politicas-negocio.md#p04) |
| 2 | — | `value=0; field='profile_multiplier'` | [P04](politicas-negocio.md#p04) |
| 3 | — | `value=-1; field='profile_history_size'` | [P04](politicas-negocio.md#p04) |
| 4 | — | `value=-1; field='profile_multiplier'` | [P04](politicas-negocio.md#p04) |
| 5 | — | `value=True; field='profile_history_size'` | [P04](politicas-negocio.md#p04) |
| 6 | — | `value=True; field='profile_multiplier'` | [P04](politicas-negocio.md#p04) |
| 7 | — | `value=1.5; field='profile_history_size'` | [P04](politicas-negocio.md#p04) |
| 8 | — | `value=1.5; field='profile_multiplier'` | [P04](politicas-negocio.md#p04) |
| 9 | — | `value='10'; field='profile_history_size'` | [P04](politicas-negocio.md#p04) |
| 10 | — | `value='10'; field='profile_multiplier'` | [P04](politicas-negocio.md#p04) |

<a id="suite-04"></a>

### 4. Possível pagamento duplicado

Fonte: [test_duplicate_payment.py](../tests/test_duplicate_payment.py). **10 funções / 22 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_duplicate_payment--test_duplicate_window_and_future_exclusion"></a>[`test_duplicate_window_and_future_exclusion`](../tests/test_duplicate_payment.py#L21) | HTTP + PostgreSQL | Testa 0, 119 e 120 segundos como duplicidade e 121 segundos/evento futuro como exclusões; quando ativo, score 30, 2FA e referência anterior sem afirmar pagamento confirmado. | [R13 — Possível duplicidade](politicas-negocio.md#r13) |
| <a id="test_duplicate_payment--test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed"></a>[`test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed`](../tests/test_duplicate_payment.py#L37) | HTTP + PostgreSQL | Após aprovação anterior, a API exibe Possível pagamento duplicado e mantém o resumo em GET/reenvio. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_duplicate_payment--test_different_payment_identity_does_not_trigger_duplicate"></a>[`test_different_payment_identity_does_not_trigger_duplicate`](../tests/test_duplicate_payment.py#L50) | HTTP + PostgreSQL | Muda isoladamente valor, pagador, conta de origem, conta de destino ou titular destinatário; cada mudança impede identificar o mesmo pagamento. | [R13 — Possível duplicidade](politicas-negocio.md#r13) |
| <a id="test_duplicate_payment--test_changed_device_and_opening_dates_do_not_hide_duplicate"></a>[`test_changed_device_and_opening_dates_do_not_hide_duplicate`](../tests/test_duplicate_payment.py#L67) | HTTP + PostgreSQL | Trocar aparelho e datas de abertura não altera a identidade das contas; duplicidade continua levando a 2FA. | [R13 — Possível duplicidade](politicas-negocio.md#r13) |
| <a id="test_duplicate_payment--test_rejected_attempt_is_not_a_possible_previous_payment"></a>[`test_rejected_attempt_is_not_a_possible_previous_payment`](../tests/test_duplicate_payment.py#L78) | HTTP + PostgreSQL | Duas tentativas de R$ 30 mil são rejeitadas por limite forte; a primeira rejeição não vira possível pagamento anterior. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[R02 — Montante](politicas-negocio.md#r02) |
| <a id="test_duplicate_payment--test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent"></a>[`test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent`](../tests/test_duplicate_payment.py#L86) | HTTP + PostgreSQL | Dois IDs concorrentes para o mesmo pagamento produzem uma aprovação e um 2FA por duplicidade; reenvios não aumentam a contagem. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_duplicate_payment--test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust"></a>[`test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust`](../tests/test_duplicate_payment.py#L98) | Unitário | Duplicidade isolada vale 30/2FA e incremento próprio zero; zerar o peso do fator permite aprovação. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_duplicate_payment--test_repository_respects_custom_duplicate_window"></a>[`test_repository_respects_custom_duplicate_window`](../tests/test_duplicate_payment.py#L113) | HTTP + PostgreSQL | Um pagamento de 60 segundos atrás entra na janela padrão de 120, mas sai quando configurada em 30 segundos. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_duplicate_payment--test_duplicate_never_overrides_a_hard_rejection"></a>[`test_duplicate_never_overrides_a_hard_rejection`](../tests/test_duplicate_payment.py#L137) | Unitário | Duplicidade junto a cinco tentativas prévias preserva rejected e origem hard_limit. | [R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[R01 — Frequência](politicas-negocio.md#r01)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_duplicate_payment--test_invalid_duplicate_window"></a>[`test_invalid_duplicate_window`](../tests/test_duplicate_payment.py#L148) | Unitário | Zero, negativo, booleano, fração e string são recusados como janela; aceita-se inteiro positivo de segundos. | [P04 — Configuração do operador](politicas-negocio.md#p04) |

**Casos individuais de `test_duplicate_window_and_future_exclusion` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_duplicate_payment--test_duplicate_window_and_future_exclusion). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `seconds=0; expected=True` | [R13](politicas-negocio.md#r13) |
| 2 | — | `seconds=119; expected=True` | [R13](politicas-negocio.md#r13) |
| 3 | — | `seconds=120; expected=True` | [R13](politicas-negocio.md#r13) |
| 4 | — | `seconds=121; expected=False` | [R13](politicas-negocio.md#r13) |
| 5 | — | `seconds=-1; expected=False` | [R13](politicas-negocio.md#r13) |

**Casos individuais de `test_different_payment_identity_does_not_trigger_duplicate` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_duplicate_payment--test_different_payment_identity_does_not_trigger_duplicate). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `field='amount'` | [R13](politicas-negocio.md#r13) |
| 2 | — | `field='payer'` | [R13](politicas-negocio.md#r13) |
| 3 | — | `field='source_account'` | [R13](politicas-negocio.md#r13) |
| 4 | — | `field='destination'` | [R13](politicas-negocio.md#r13) |
| 5 | — | `field='recipient'` | [R13](politicas-negocio.md#r13) |

**Casos individuais de `test_invalid_duplicate_window` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_duplicate_payment--test_invalid_duplicate_window). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `value=0` | [P04](politicas-negocio.md#p04) |
| 2 | — | `value=-1` | [P04](politicas-negocio.md#p04) |
| 3 | — | `value=True` | [P04](politicas-negocio.md#p04) |
| 4 | — | `value=1.5` | [P04](politicas-negocio.md#p04) |
| 5 | — | `value='120'` | [P04](politicas-negocio.md#p04) |

<a id="suite-05"></a>

### 5. Aparelhos, canal e horário

Fonte: [test_access_patterns.py](../tests/test_access_patterns.py). **9 funções / 25 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_access_patterns--test_night_rule_uses_app_and_brasilia_boundaries"></a>[`test_night_rule_uses_app_and_brasilia_boundaries`](../tests/test_access_patterns.py#L38) | Unitário | Verifica 19:59:59, 20:00, 05:59:59 e 06:00, conversão de fuso e APP/App/espaços; a noite é [20h,06h) em Brasília e o sinal não declara checagem de limite bancário. | [R12 — Uso noturno do app](politicas-negocio.md#r12) |
| <a id="test_access_patterns--test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits"></a>[`test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits`](../tests/test_access_patterns.py#L48) | Unitário | internet_banking, web, atm e api ficam fora do sinal noturno; todos continuam sujeitos à rejeição por frequência. | [R12 — Uso noturno do app](politicas-negocio.md#r12)<br>[R01 — Frequência](politicas-negocio.md#r01) |
| <a id="test_access_patterns--test_configured_night_start_controls_the_signal"></a>[`test_configured_night_start_controls_the_signal`](../tests/test_access_patterns.py#L66) | Unitário | Com início configurado às 22h, 21:59:59 não é noite e 22:00 é noite; metadados acompanham o parâmetro. | [R12 — Uso noturno do app](politicas-negocio.md#r12)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_access_patterns--test_invalid_access_policy"></a>[`test_invalid_access_policy`](../tests/test_access_patterns.py#L90) | Unitário | Rejeita horas fora da faixa, booleano, início igual ao fim e limites de diversidade inferiores a dois. | [P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_access_patterns--test_shared_device_counts_distinct_owners_and_excludes_old_future_events"></a>[`test_shared_device_counts_distinct_owners_and_excludes_old_future_events`](../tests/test_access_patterns.py#L95) | HTTP + PostgreSQL | Várias contas do mesmo titular contam uma pessoa; eventos >24h e futuros são excluídos; terceiro titular atual ativa compartilhamento. | [R10 — Aparelho compartilhado](politicas-negocio.md#r10)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_access_patterns--test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate"></a>[`test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate`](../tests/test_access_patterns.py#L115) | HTTP + PostgreSQL | Repetições do mesmo aparelho e contas distintas do mesmo titular são agregadas; dois aparelhos anteriores + atual desconhecido ativam a regra. | [R11 — Múltiplos aparelhos](politicas-negocio.md#r11)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_access_patterns--test_shared_device_concurrency_sees_prior_commits"></a>[`test_shared_device_concurrency_sees_prior_commits`](../tests/test_access_patterns.py#L127) | HTTP + PostgreSQL | Três titulares concorrentes no mesmo aparelho observam contagens 1,2,3; somente o terceiro aciona compartilhamento. | [R10 — Aparelho compartilhado](politicas-negocio.md#r10)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_access_patterns--test_repository_recognizes_habitual_night_use"></a>[`test_repository_recognizes_habitual_night_use`](../tests/test_access_patterns.py#L141) | HTTP + PostgreSQL | Histórico aprovado noturno impede a penalização por horário, mesmo com aparelho novo. | [R12 — Uso noturno do app](politicas-negocio.md#r12)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_access_patterns--test_repository_novel_app_night_combines_context_with_device"></a>[`test_repository_novel_app_night_combines_context_with_device`](../tests/test_access_patterns.py#L151) | HTTP + PostgreSQL | Três aprovações diurnas, app noturno, R$ 500 e aparelho novo somam 15+20=35 e exigem 2FA. | [R12 — Uso noturno do app](politicas-negocio.md#r12)<br>[R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |

**Casos individuais de `test_night_rule_uses_app_and_brasilia_boundaries` (8)**

Todos verificam o cenário e as políticas da [análise da função](#test_access_patterns--test_night_rule_uses_app_and_brasilia_boundaries). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | before-night | `channel='app'; date='2026-10-17T19:59:59-03:00'; night=False` | [R12](politicas-negocio.md#r12) |
| 2 | night-start-inclusive | `channel='app'; date='2026-10-17T20:00:00-03:00'; night=True` | [R12](politicas-negocio.md#r12) |
| 3 | last-night-second | `channel='app'; date='2026-10-18T05:59:59-03:00'; night=True` | [R12](politicas-negocio.md#r12) |
| 4 | night-end-exclusive | `channel='app'; date='2026-10-18T06:00:00-03:00'; night=False` | [R12](politicas-negocio.md#r12) |
| 5 | timezone-converted-to-brasilia | `channel='app'; date='2026-10-18T02:00:00+03:00'; night=True` | [R12](politicas-negocio.md#r12) |
| 6 | uppercase-channel | `channel='APP'; date='2026-10-17T23:00:00-03:00'; night=True` | [R12](politicas-negocio.md#r12) |
| 7 | mixed-case-channel | `channel='App'; date='2026-10-17T23:00:00-03:00'; night=True` | [R12](politicas-negocio.md#r12) |
| 8 | trimmed-channel | `channel=' app '; date='2026-10-17T23:00:00-03:00'; night=True` | [R12](politicas-negocio.md#r12) |

**Casos individuais de `test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_access_patterns--test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `channel='internet_banking'` | [R12](politicas-negocio.md#r12)<br>[R01](politicas-negocio.md#r01) |
| 2 | — | `channel='web'` | [R12](politicas-negocio.md#r12)<br>[R01](politicas-negocio.md#r01) |
| 3 | — | `channel='atm'` | [R12](politicas-negocio.md#r12)<br>[R01](politicas-negocio.md#r01) |
| 4 | — | `channel='api'` | [R12](politicas-negocio.md#r12)<br>[R01](politicas-negocio.md#r01) |

**Casos individuais de `test_configured_night_start_controls_the_signal` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_access_patterns--test_configured_night_start_controls_the_signal). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | before-configured-night-start | `date='2026-10-17T21:59:59-03:00'; night=False` | [R12](politicas-negocio.md#r12)<br>[P04](politicas-negocio.md#p04) |
| 2 | at-configured-night-start | `date='2026-10-17T22:00:00-03:00'; night=True` | [R12](politicas-negocio.md#r12)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_invalid_access_policy` (6)**

Todos verificam o cenário e as políticas da [análise da função](#test_access_patterns--test_invalid_access_policy). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'night_start_hour': 24}` | [P04](politicas-negocio.md#p04) |
| 2 | — | `changes={'night_end_hour': -1}` | [P04](politicas-negocio.md#p04) |
| 3 | — | `changes={'night_start_hour': True}` | [P04](politicas-negocio.md#p04) |
| 4 | — | `changes={'night_start_hour': 6}` | [P04](politicas-negocio.md#p04) |
| 5 | — | `changes={'device_owner_limit': 1}` | [P04](politicas-negocio.md#p04) |
| 6 | — | `changes={'payer_device_limit': 1}` | [P04](politicas-negocio.md#p04) |

<a id="suite-06"></a>

### 6. Prioridade e limiares de decisão

Fonte: [test_scoring_policy.py](../tests/test_scoring_policy.py). **5 funções / 27 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_scoring_policy--test_score_boundaries_and_rejection_factor_guard"></a>[`test_score_boundaries_and_rejection_factor_guard`](../tests/test_scoring_policy.py#L26) | Unitário | Testa 29/30/31, 79/80 com um fator e 79/80/81 com dois: 30 inicia 2FA, mas rejeição por score só ocorre com pelo menos dois fatores positivos. | [P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_scoring_policy--test_decision_uses_configured_thresholds"></a>[`test_decision_uses_configured_thresholds`](../tests/test_scoring_policy.py#L50) | Unitário | Configura 2FA=45 e rejeição=60; verifica 44/45/59/60 com dois fatores e persistência dos limiares na evidência. | [P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_scoring_policy--test_configured_rejection_requires_three_positive_factors"></a>[`test_configured_rejection_requires_three_positive_factors`](../tests/test_scoring_policy.py#L76) | Unitário | Com mínimo configurado em três, score ≥80 com dois fatores permanece em 2FA; três fatores permitem rejeitar. | [P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_scoring_policy--test_missing_reference_priority_survives_zero_weights"></a>[`test_missing_reference_priority_survives_zero_weights`](../tests/test_scoring_policy.py#L128) | Unitário | Zera pesos de exposição/atividade: sem referência a R$ 500 exige 2FA com score zero; R$ 30 mil mantém rejeição forte, tanto no primeiro Pix quanto após tentativas. | [P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[R02 — Montante](politicas-negocio.md#r02) |
| <a id="test_scoring_policy--test_invalid_policy_cannot_be_activated"></a>[`test_invalid_policy_cannot_be_activated`](../tests/test_scoring_policy.py#L164) | Unitário | Recusa limiares inválidos, grupos fora da faixa, booleanos e pesos negativos, >100 ou fracionários. | [P04 — Configuração do operador](politicas-negocio.md#p04) |

**Casos individuais de `test_score_boundaries_and_rejection_factor_guard` (8)**

Todos verificam o cenário e as políticas da [análise da função](#test_scoring_policy--test_score_boundaries_and_rejection_factor_guard). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | below-two-factor | `points=29; account_points=0; expected='approved'` | [P01](politicas-negocio.md#p01) |
| 2 | at-two-factor | `points=30; account_points=0; expected='two_factor_required'` | [P01](politicas-negocio.md#p01) |
| 3 | above-two-factor | `points=31; account_points=0; expected='two_factor_required'` | [P01](politicas-negocio.md#p01) |
| 4 | one-factor-below-rejection | `points=79; account_points=0; expected='two_factor_required'` | [P01](politicas-negocio.md#p01) |
| 5 | one-factor-at-rejection | `points=80; account_points=0; expected='two_factor_required'` | [P01](politicas-negocio.md#p01) |
| 6 | two-factors-below-rejection | `points=64; account_points=15; expected='two_factor_required'` | [P01](politicas-negocio.md#p01) |
| 7 | two-factors-at-rejection | `points=65; account_points=15; expected='rejected'` | [P01](politicas-negocio.md#p01) |
| 8 | two-factors-above-rejection | `points=66; account_points=15; expected='rejected'` | [P01](politicas-negocio.md#p01) |

**Casos individuais de `test_decision_uses_configured_thresholds` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_scoring_policy--test_decision_uses_configured_thresholds). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | below-configured-two-factor | `points=44; expected='approved'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |
| 2 | at-configured-two-factor | `points=45; expected='two_factor_required'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |
| 3 | below-configured-rejection | `points=59; expected='two_factor_required'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |
| 4 | at-configured-rejection | `points=60; expected='rejected'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_configured_rejection_requires_three_positive_factors` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_scoring_policy--test_configured_rejection_requires_three_positive_factors). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | two-factors-are-insufficient | `known_destination=True; expected_groups=2; expected='two_factor_required'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |
| 2 | three-positive-factors-allow-rejection | `known_destination=False; expected_groups=3; expected='rejected'` | [P01](politicas-negocio.md#p01)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_missing_reference_priority_survives_zero_weights` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_scoring_policy--test_missing_reference_priority_survives_zero_weights). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | first-pix-needs-two-factor-at-zero-score | `registered=0; amount=50000; expected='two_factor_required'; source='first_transaction'; exposure_rule='first_transaction'` | [P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 2 | missing-reference-needs-two-factor-at-zero-score | `registered=2; amount=50000; expected='two_factor_required'; source='insufficient_history'; exposure_rule='insufficient_amount_history'` | [P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 3 | hard-limit-precedes-first-pix-two-factor | `registered=0; amount=3000000; expected='rejected'; source='hard_limit'; exposure_rule='first_transaction'` | [P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 4 | hard-limit-precedes-missing-reference-two-factor | `registered=2; amount=3000000; expected='rejected'; source='hard_limit'; exposure_rule='insufficient_amount_history'` | [P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |

**Casos individuais de `test_invalid_policy_cannot_be_activated` (9)**

Todos verificam o cenário e as políticas da [análise da função](#test_scoring_policy--test_invalid_policy_cannot_be_activated). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'two_factor_threshold': 0}` | [P04](politicas-negocio.md#p04) |
| 2 | — | `changes={'rejection_threshold': 101}` | [P04](politicas-negocio.md#p04) |
| 3 | — | `changes={'two_factor_threshold': 80}` | [P04](politicas-negocio.md#p04) |
| 4 | — | `changes={'minimum_rejection_groups': 0}` | [P04](politicas-negocio.md#p04) |
| 5 | — | `changes={'minimum_rejection_groups': 9}` | [P04](politicas-negocio.md#p04) |
| 6 | — | `changes={'rejection_threshold': True}` | [P04](politicas-negocio.md#p04) |
| 7 | — | `changes={'weights': replace(RuleWeights(), unfamiliar_device=-1)}` | [P04](politicas-negocio.md#p04) |
| 8 | — | `changes={'weights': replace(RuleWeights(), unfamiliar_device=101)}` | [P04](politicas-negocio.md#p04) |
| 9 | — | `changes={'weights': replace(RuleWeights(), unfamiliar_device=1.5)}` | [P04](politicas-negocio.md#p04) |

<a id="suite-07"></a>

### 7. Ponderação, tetos e configuração

Fonte: [test_risk_factors.py](../tests/test_risk_factors.py). **8 funções / 19 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_risk_factors--test_fractional_factor_weight_is_truncated_before_decision_and_explained"></a>[`test_fractional_factor_weight_is_truncated_before_decision_and_explained`](../tests/test_risk_factors.py#L20) | Unitário | Peso de perfil em 37% transforma 80 em 29, e não 30; aprova e registra valor bruto, ponderado, teto e contribuição. | [P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_risk_factors--test_increasing_factor_weights_can_block_a_transaction"></a>[`test_increasing_factor_weights_can_block_a_transaction`](../tests/test_risk_factors.py#L41) | Unitário | Perfil 80 mais conta ponderada a 200%, com teto da conta elevado a 30, resulta em score final 100 e rejeição por dois fatores. | [P02 — Score e tetos](politicas-negocio.md#p02)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_risk_factors--test_rule_remapping_changes_factor_cap_and_rejection_guard"></a>[`test_rule_remapping_changes_factor_cap_and_rejection_guard`](../tests/test_risk_factors.py#L55) | Unitário | Move conta nova para profile; os sinais passam a compartilhar teto e contam um fator, impedindo rejeição por score isolado. | [P02 — Score e tetos](politicas-negocio.md#p02)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score"></a>[`test_related_rules_share_one_factor_and_reconstruct_capped_score`](../tests/test_risk_factors.py#L96) | Unitário | Destinatário soma 30 e contribui 25; aparelhos somam 70 e contribuem 40. Verifica contribuições efetivas e desempate determinístico dentro do teto. | [P02 — Score e tetos](politicas-negocio.md#p02)<br>[R06 — Destino recente](politicas-negocio.md#r06)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[R10 — Aparelho compartilhado](politicas-negocio.md#r10)<br>[R11 — Múltiplos aparelhos](politicas-negocio.md#r11) |
| <a id="test_risk_factors--test_invalid_factor_weight"></a>[`test_invalid_factor_weight`](../tests/test_risk_factors.py#L115) | Unitário | Recusa -1, 201, booleano, fração e string; peso percentual exige inteiro entre 0 e 200. | [P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_risk_factors--test_every_rule_references_a_valid_factor"></a>[`test_every_rule_references_a_valid_factor`](../tests/test_risk_factors.py#L120) | Unitário | Confere que pesos e mapeamentos cobrem os mesmos códigos; fator inexistente é recusado. | [P04 — Configuração do operador](politicas-negocio.md#p04)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_risk_factors--test_load_partial_policy_and_default_configuration"></a>[`test_load_partial_policy_and_default_configuration`](../tests/test_risk_factors.py#L127) | Unitário | Confere JSON padrão igual aos defaults; configuração parcial altera device para 50% e preserva demais padrões. | [P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_risk_factors--test_invalid_file_cannot_be_activated"></a>[`test_invalid_file_cannot_be_activated`](../tests/test_risk_factors.py#L148) | Unitário | Recusa raiz/seções de tipo incorreto, campo desconhecido, fator inválido e limiares inconsistentes. | [P04 — Configuração do operador](politicas-negocio.md#p04) |

**Casos individuais de `test_related_rules_share_one_factor_and_reconstruct_capped_score` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | counterparty-tie-break-consumes-cap-25 | `factor='counterparty'; history_changes={'known_destination': False}; young_destination=True; raw=30; points=25; contributions={'new_destination_account': 15, 'unfamiliar_destination': 10}; expected='approved'` | [P02](politicas-negocio.md#p02)<br>[R06](politicas-negocio.md#r06)<br>[R07](politicas-negocio.md#r07)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10)<br>[R11](politicas-negocio.md#r11) |
| 2 | three-device-rules-remain-one-factor-capped-at-40 | `factor='device'; history_changes={'known_device': False, 'device_other_owners': 2, 'payer_other_devices': 2}; young_destination=False; raw=70; points=40; contributions={'shared_device': 30, 'multiple_devices': 10, 'unfamiliar_device': 0}; expected='two_factor_required'` | [P02](politicas-negocio.md#p02)<br>[R06](politicas-negocio.md#r06)<br>[R07](politicas-negocio.md#r07)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10)<br>[R11](politicas-negocio.md#r11) |

**Casos individuais de `test_invalid_factor_weight` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_risk_factors--test_invalid_factor_weight). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `value=-1` | [P04](politicas-negocio.md#p04) |
| 2 | — | `value=201` | [P04](politicas-negocio.md#p04) |
| 3 | — | `value=True` | [P04](politicas-negocio.md#p04) |
| 4 | — | `value=0.5` | [P04](politicas-negocio.md#p04) |
| 5 | — | `value='100'` | [P04](politicas-negocio.md#p04) |

**Casos individuais de `test_invalid_file_cannot_be_activated` (7)**

Todos verificam o cenário e as políticas da [análise da função](#test_risk_factors--test_invalid_file_cannot_be_activated). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `data=[]` | [P04](politicas-negocio.md#p04) |
| 2 | — | `data={'scoring': []}` | [P04](politicas-negocio.md#p04) |
| 3 | — | `data={'scoring': {'factor_weights': []}}` | [P04](politicas-negocio.md#p04) |
| 4 | — | `data={'scoring': {'factor_weights': {'typo': 20}}}` | [P04](politicas-negocio.md#p04) |
| 5 | — | `data={'scoring': {'rule_factors': {'new_source_account': 'typo'}}}` | [P04](politicas-negocio.md#p04) |
| 6 | — | `data={'scoring': {'rejection_threshold': 20}}` | [P04](politicas-negocio.md#p04) |
| 7 | — | `data={'unknown': 1}` | [P04](politicas-negocio.md#p04) |

<a id="suite-08"></a>

### 8. Resultados integrados do score

Fonte: [test_risk_score.py](../tests/test_risk_score.py). **9 funções / 9 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_risk_score--test_first_pix_requests_two_factor_and_saves_explanation"></a>[`test_first_pix_requests_two_factor_and_saves_explanation`](../tests/test_risk_score.py#L45) | HTTP + PostgreSQL | Primeiro Pix de R$ 500 produz score 30, 2FA e causa first_transaction; GET e reenvio preservam a análise. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_risk_score--test_approved_history_makes_device_and_young_destination_familiar"></a>[`test_approved_history_makes_device_and_young_destination_familiar`](../tests/test_risk_score.py#L58) | HTTP + PostgreSQL | Três aprovações tornam aparelho/destino conhecidos; conta de destino jovem já conhecida não pontua; resultado score zero/aprovado. | [R06 — Destino recente](politicas-negocio.md#r06)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_risk_score--test_weak_device_signal_alone_approves"></a>[`test_weak_device_signal_alone_approves`](../tests/test_risk_score.py#L73) | HTTP + PostgreSQL | Aparelho desconhecido isolado vale 20 e mantém aprovação. | [R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_risk_score--test_two_weak_groups_combine_into_two_factor"></a>[`test_two_weak_groups_combine_into_two_factor`](../tests/test_risk_score.py#L84) | HTTP + PostgreSQL | Aparelho desconhecido 20 + destinatário desconhecido 15 somam 35 e exigem 2FA. | [R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_risk_score--test_related_counterparty_signals_are_capped"></a>[`test_related_counterparty_signals_are_capped`](../tests/test_risk_score.py#L94) | HTTP + PostgreSQL | Destino jovem e desconhecido somam 30 brutos, mas teto reduz a 25; sem outros sinais aprova. | [R06 — Destino recente](politicas-negocio.md#r06)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_risk_score--test_high_profile_signal_alone_requires_two_factor"></a>[`test_high_profile_signal_alone_requires_two_factor`](../tests/test_risk_score.py#L105) | HTTP + PostgreSQL | Valor cinco vezes a referência produz score 80/high, sem limite forte; fator isolado exige 2FA. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_risk_score--test_high_profile_plus_new_account_rejects"></a>[`test_high_profile_plus_new_account_rejects`](../tests/test_risk_score.py#L115) | HTTP + PostgreSQL | Desvio de perfil 80 + conta de origem nova 15 produzem score 95 e rejected. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[R05 — Origem recente](politicas-negocio.md#r05)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_risk_score--test_factor_sum_can_exceed_final_score_cap"></a>[`test_factor_sum_can_exceed_final_score_cap`](../tests/test_risk_score.py#L126) | HTTP + PostgreSQL | Combina fatores até soma 140; score público fica 100 e a redução pelo teto permite reconstruir a soma auditável. | [P02 — Score e tetos](politicas-negocio.md#p02)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_risk_score--test_activity_group_cap_preserves_all_hard_reasons"></a>[`test_activity_group_cap_preserves_all_hard_reasons`](../tests/test_risk_score.py#L140) | HTTP + PostgreSQL | Frequência e montante fortes simultâneos compartilham teto 80, preservam as duas causas e rejeitam. | [R01 — Frequência](politicas-negocio.md#r01)<br>[R02 — Montante](politicas-negocio.md#r02)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |

<a id="suite-09"></a>

### 9. Confiança por relação e atribuição da evidência

Fonte: [test_contextual_trust.py](../tests/test_contextual_trust.py). **10 funções / 25 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_contextual_trust--test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence"></a>[`test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence`](../tests/test_contextual_trust.py#L33) | Unitário | Relação com amostras suficientes e valor compatível zera perfil de 80 para 0; aprova, preserva pontos originais e deixa causas de intervenção vazias. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_contextual_trust--test_insufficient_or_invalid_evidence_cannot_grant_attenuation"></a>[`test_insufficient_or_invalid_evidence_cannot_grant_attenuation`](../tests/test_contextual_trust.py#L57) | Unitário | Quatro amostras do pagador, duas da relação, um dia, relação vazia ou valor zero impedem confiança; perfil continua 80/2FA com motivo explícito. | [P05 — Confiança contextual](politicas-negocio.md#p05) |
| <a id="test_contextual_trust--test_relationship_compatibility_boundaries_are_inclusive_and_exact"></a>[`test_relationship_compatibility_boundaries_are_inclusive_and_exact`](../tests/test_contextual_trust.py#L68) | Unitário | Para mediana de R$ 2.000, testa 99.999/100.000/400.000/400.001 centavos; somente o intervalo inclusivo de 50% a 200% reduz o perfil. | [P05 — Confiança contextual](politicas-negocio.md#p05) |
| <a id="test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls"></a>[`test_familiar_relationship_never_neutralizes_independent_controls`](../tests/test_contextual_trust.py#L82) | Unitário | Mesmo com perfil zerado, permanecem aparelho novo 20, frequência/montante fortes 80 e compartilhamento 30, com suas respectivas decisões. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[R01 — Frequência](politicas-negocio.md#r01)<br>[R02 — Montante](politicas-negocio.md#r02)<br>[R10 — Aparelho compartilhado](politicas-negocio.md#r10) |
| <a id="test_contextual_trust--test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar"></a>[`test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar`](../tests/test_contextual_trust.py#L91) | Unitário | Referências de um centavo não tornam R$ 2.000 habitual; desabilitar confiança mantém perfil 80. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_contextual_trust--test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust"></a>[`test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust`](../tests/test_contextual_trust.py#L99) | Unitário | Mediana de 101/102 centavos preserva meio centavo pelo dobro inteiro; histórico legado de pendência não satisfaz confiança. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_contextual_trust--test_invalid_contextual_policy_fails_before_accepting_requests"></a>[`test_invalid_contextual_policy_fails_before_accepting_requests`](../tests/test_contextual_trust.py#L117) | Unitário | Recusa flag não booleana, amostra insuficiente/incoerente, dias excessivos e intervalo de compatibilidade que exclui 100%. | [P04 — Configuração do operador](politicas-negocio.md#p04)<br>[P05 — Confiança contextual](politicas-negocio.md#p05) |
| <a id="test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender"></a>[`test_destination_evidence_intervenes_without_accusing_the_sender`](../tests/test_contextual_trust.py#L122) | Unitário | Conta de origem nova + destino novo/desconhecido levam a score 40/2FA; os sinais do destino/relação têm sujeitos distintos e incremento próprio zero. | [R05 — Origem recente](politicas-negocio.md#r05)<br>[R06 — Destino recente](politicas-negocio.md#r06)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_contextual_trust--test_mixed_sender_and_destination_evidence_preserves_only_own_increment"></a>[`test_mixed_sender_and_destination_evidence_preserves_only_own_increment`](../tests/test_contextual_trust.py#L139) | Unitário | Aparelho novo + destino desconhecido somam 35, mas só os 20 do aparelho geram incremento próprio de 5. | [R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_contextual_trust--test_hypothetical_critical_destination_detector_cannot_create_own_risk"></a>[`test_hypothetical_critical_destination_detector_cannot_create_own_risk`](../tests/test_contextual_trust.py#L157) | Unitário | Injeta detector forte de destino somente no teste: rejeita a transação, atribui a causa ao destino e não acrescenta suspeita própria. Não implementa blacklist na API. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

**Casos individuais de `test_insufficient_or_invalid_evidence_cannot_grant_attenuation` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_contextual_trust--test_insufficient_or_invalid_evidence_cannot_grant_attenuation). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'payer_reference_values': (10000,) * 4}; reason='insufficient_payer_history'` | [P05](politicas-negocio.md#p05) |
| 2 | — | `changes={'relationship_reference_values': (200000,) * 2}; reason='insufficient_relationship_history'` | [P05](politicas-negocio.md#p05) |
| 3 | — | `changes={'relationship_received_days': 1}; reason='insufficient_received_days'` | [P05](politicas-negocio.md#p05) |
| 4 | — | `changes={'relationship_reference_values': ()}; reason='insufficient_relationship_history'` | [P05](politicas-negocio.md#p05) |
| 5 | — | `changes={'relationship_reference_values': (0, 200000, 200000)}; reason='invalid_reference'` | [P05](politicas-negocio.md#p05) |

**Casos individuais de `test_relationship_compatibility_boundaries_are_inclusive_and_exact` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_contextual_trust--test_relationship_compatibility_boundaries_are_inclusive_and_exact). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `amount=99999; applied=False` | [P05](politicas-negocio.md#p05) |
| 2 | — | `amount=100000; applied=True` | [P05](politicas-negocio.md#p05) |
| 3 | — | `amount=400000; applied=True` | [P05](politicas-negocio.md#p05) |
| 4 | — | `amount=400001; applied=False` | [P05](politicas-negocio.md#p05) |

**Casos individuais de `test_familiar_relationship_never_neutralizes_independent_controls` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'known_device': False}; rule='unfamiliar_device'; score=20; status='approved'` | [P05](politicas-negocio.md#p05)<br>[R09](politicas-negocio.md#r09)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |
| 2 | — | `changes={'recent_count': 5}; rule='velocity_above_limit'; score=80; status='rejected'` | [P05](politicas-negocio.md#p05)<br>[R09](politicas-negocio.md#r09)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |
| 3 | — | `changes={'recent_amount': 2800000}; rule='accumulated_amount_above_limit'; score=80; status='rejected'` | [P05](politicas-negocio.md#p05)<br>[R09](politicas-negocio.md#r09)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |
| 4 | — | `changes={'device_other_owners': 2}; rule='shared_device'; score=30; status='two_factor_required'` | [P05](politicas-negocio.md#p05)<br>[R09](politicas-negocio.md#r09)<br>[R01](politicas-negocio.md#r01)<br>[R02](politicas-negocio.md#r02)<br>[R10](politicas-negocio.md#r10) |

**Casos individuais de `test_invalid_contextual_policy_fails_before_accepting_requests` (6)**

Todos verificam o cenário e as políticas da [análise da função](#test_contextual_trust--test_invalid_contextual_policy_fails_before_accepting_requests). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'enabled': 1}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |
| 2 | — | `changes={'history_size': 2}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |
| 3 | — | `changes={'minimum_received_days': 4}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |
| 4 | — | `changes={'minimum_ratio_percent': 101}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |
| 5 | — | `changes={'maximum_ratio_percent': 99}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |
| 6 | — | `changes={'history_size': True}` | [P04](politicas-negocio.md#p04)<br>[P05](politicas-negocio.md#p05) |

<a id="suite-10"></a>

### 10. Confiança contextual no PostgreSQL e HTTP

Fonte: [test_contextual_trust_db.py](../tests/test_contextual_trust_db.py). **6 funções / 6 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_contextual_trust_db--test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals"></a>[`test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals`](../tests/test_contextual_trust_db.py#L60) | PostgreSQL + controlador/repositório | Só duas aprovações elegíveis de 101/102 centavos entram nas referências; exclui pendência, rejeição, recepção/evento futuros, >30 dias e aprovação com limite forte. Tentativas válidas continuam no histórico bruto. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_contextual_trust_db--test_backdated_requests_received_on_one_day_cannot_manufacture_trust"></a>[`test_backdated_requests_received_on_one_day_cannot_manufacture_trust`](../tests/test_contextual_trust_db.py#L88) | PostgreSQL + controlador/repositório | Cinco eventos declarados em dias diferentes mas recebidos no mesmo dia contam um único dia de confiança. | [P05 — Confiança contextual](politicas-negocio.md#p05) |
| <a id="test_contextual_trust_db--test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk"></a>[`test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk`](../tests/test_contextual_trust_db.py#L99) | PostgreSQL + controlador/repositório | Incremento legado de 25 fica consultável, mas apenas o incremento 20 com sender-evidence-v2 entra em conta/titular. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_contextual_trust_db--test_contextual_decision_is_persisted_and_retry_and_get_preserve_it"></a>[`test_contextual_decision_is_persisted_and_retry_and_get_preserve_it`](../tests/test_contextual_trust_db.py#L128) | PostgreSQL + controlador/repositório | Persiste aprovação com perfil atenuado, incremento zero e política original; GET/reenvio após troca de política mantêm uma única linha. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_contextual_trust_db--test_destination_attempts_remain_in_history_without_tainting_normal_next_payment"></a>[`test_destination_attempts_remain_in_history_without_tainting_normal_next_payment`](../tests/test_contextual_trust_db.py#L162) | PostgreSQL + controlador/repositório | Seis intervenções por destino, espaçadas além da janela de frequência, mantêm acumulado próprio zero; Pix normal seguinte aprova e as nove tentativas permanecem contáveis. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_contextual_trust_db--test_post_get_and_retry_preserve_contextual_response_without_duplicating_history"></a>[`test_post_get_and_retry_preserve_contextual_response_without_duplicating_history`](../tests/test_contextual_trust_db.py#L201) | HTTP + PostgreSQL | Aprovação contextual via HTTP é preservada; resumo não expõe confiança interna nem lista perfil com contribuição zero; existe uma linha para o ID. | [P05 — Confiança contextual](politicas-negocio.md#p05)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

<a id="suite-11"></a>

### 11. Desconfiança acumulada da conta

Fonte: [test_account_untrust.py](../tests/test_account_untrust.py). **14 funções / 35 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_account_untrust--test_increment_uses_current_rule_evidence_and_never_account_score"></a>[`test_increment_uses_current_rule_evidence_and_never_account_score`](../tests/test_account_untrust.py#L26) | Unitário | Perfil com contribuição 80 gera incremento 20; histórico 20 passa a 40, sem somar acumulado ao risk_score transacional. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_account_thresholds_and_repeated_evidence_guard"></a>[`test_account_thresholds_and_repeated_evidence_guard`](../tests/test_account_untrust.py#L51) | Unitário | Testa acumulados 0/39/40/59/60/79/80/100 e contagens distintas: 40 inicia 2FA, 60 indica aviso; mesmo 100 não rejeita com bloqueio padrão desligado. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_active_block_does_not_refresh_itself_even_on_velocity_risk"></a>[`test_active_block_does_not_refresh_itself_even_on_velocity_risk`](../tests/test_account_untrust.py#L63) | Unitário | Com histórico 100/cinco eventos e novo limite forte, preserva rejeição transacional, mas suprime incremento para não renovar indefinidamente a restrição. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[R01 — Frequência](politicas-negocio.md#r01) |
| <a id="test_account_untrust--test_first_transaction_and_account_age_alone_do_not_build_untrust"></a>[`test_first_transaction_and_account_age_alone_do_not_build_untrust`](../tests/test_account_untrust.py#L76) | Unitário | Primeiro Pix ≥R$ 500 e conta nova somam 45, mas não são evidências elegíveis para acumulado próprio. | [R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R05 — Origem recente](politicas-negocio.md#r05)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_single_low_risk_novelty_does_not_accumulate"></a>[`test_single_low_risk_novelty_does_not_accumulate`](../tests/test_account_untrust.py#L89) | Unitário | Aparelho novo isolado vale 20, aprova e não incrementa acumulado por ficar abaixo do limiar transacional de 30. | [R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_disabled_account_control_ignores_history_and_current_evidence"></a>[`test_disabled_account_control_ignores_history_and_current_evidence`](../tests/test_account_untrust.py#L100) | Unitário | enabled=false zera score/incremento e não indica aviso, mesmo com histórico 100. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_account_untrust--test_notification_indicates_threshold_crossing_without_claiming_delivery"></a>[`test_notification_indicates_threshold_crossing_without_claiming_delivery`](../tests/test_account_untrust.py#L109) | Unitário | Passagem 40→60 marca threshold_crossed e indicated_only; acima de 60 mantém aviso requerido, sem marcar novo cruzamento. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_invalid_untrust_policy_fails_startup"></a>[`test_invalid_untrust_policy_fails_startup`](../tests/test_account_untrust.py#L131) | Unitário | Recusa flags inválidas, janela zero, divisor booleano, limiares incoerentes, incremento >25 e mínimo de eventos <2. | [P04 — Configuração do operador](politicas-negocio.md#p04)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score"></a>[`test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score`](../tests/test_account_untrust.py#L136) | HTTP + PostgreSQL | Quatro desvios geram 20→40→60→80; Pix normal seguinte tem score zero, mas exige 2FA pelo acumulado, sem novo incremento. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_account_untrust--test_untrust_is_per_account_not_all_accounts_of_same_owner"></a>[`test_untrust_is_per_account_not_all_accounts_of_same_owner`](../tests/test_account_untrust.py#L150) | HTTP + PostgreSQL | Duas evidências deixam conta original em 40; outra conta do mesmo titular tem account_untrust zero. A agregação por titular pertence a entity_risk. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_account_untrust--test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points"></a>[`test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points`](../tests/test_account_untrust.py#L163) | HTTP + PostgreSQL | Alterar data de abertura não reinicia identidade/acumulado; payload inválido não cria evidência. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_account_untrust--test_concurrent_account_attempts_cannot_lose_increments"></a>[`test_concurrent_account_attempts_cannot_lose_increments`](../tests/test_account_untrust.py#L176) | HTTP + PostgreSQL | Quatro tentativas concorrentes preservam 20/40/60/80 e apenas um cruzamento do limiar de aviso. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_account_untrust--test_server_clock_not_caller_event_time_is_passed_to_account_history"></a>[`test_server_clock_not_caller_event_time_is_passed_to_account_history`](../tests/test_account_untrust.py#L185) | Unitário | Pedido retrodatado usa o instante atual do servidor para consultar acumulado e preserva a exigência de 2FA. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_account_untrust--test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control"></a>[`test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control`](../tests/test_account_untrust.py#L216) | Unitário | Com bloqueio optativo ligado, 79 pontos ou só três eventos não rejeitam; 80+quatro eventos rejeitam; controle anterior nunca é relaxado. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |

**Casos individuais de `test_account_thresholds_and_repeated_evidence_guard` (9)**

Todos verificam o cenário e as políticas da [análise da função](#test_account_untrust--test_account_thresholds_and_repeated_evidence_guard). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `points=0; events=0; action='none'; notify=False` | [P06](politicas-negocio.md#p06) |
| 2 | — | `points=39; events=2; action='none'; notify=False` | [P06](politicas-negocio.md#p06) |
| 3 | — | `points=40; events=2; action='two_factor_required'; notify=False` | [P06](politicas-negocio.md#p06) |
| 4 | — | `points=59; events=3; action='two_factor_required'; notify=False` | [P06](politicas-negocio.md#p06) |
| 5 | — | `points=60; events=3; action='two_factor_required'; notify=True` | [P06](politicas-negocio.md#p06) |
| 6 | — | `points=79; events=4; action='two_factor_required'; notify=True` | [P06](politicas-negocio.md#p06) |
| 7 | — | `points=80; events=4; action='two_factor_required'; notify=True` | [P06](politicas-negocio.md#p06) |
| 8 | — | `points=100; events=1; action='two_factor_required'; notify=True` | [P06](politicas-negocio.md#p06) |
| 9 | — | `points=100; events=4; action='two_factor_required'; notify=True` | [P06](politicas-negocio.md#p06) |

**Casos individuais de `test_invalid_untrust_policy_fails_startup` (7)**

Todos verificam o cenário e as políticas da [análise da função](#test_account_untrust--test_invalid_untrust_policy_fails_startup). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'enabled': 1}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 2 | — | `changes={'window_hours': 0}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 3 | — | `changes={'score_divisor': True}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 4 | — | `changes={'notification_threshold': 101}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 5 | — | `changes={'rejection_threshold': 60}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 6 | — | `changes={'maximum_increment': 26}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |
| 7 | — | `changes={'minimum_rejection_events': 1}` | [P04](politicas-negocio.md#p04)<br>[P06](politicas-negocio.md#p06) |

**Casos individuais de `test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control` (8)**

Todos verificam o cenário e as políticas da [análise da função](#test_account_untrust--test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | below-block | `original='approved'; points=79; events=4; action='two_factor_required'; expected='two_factor_required'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 2 | too-few-events | `original='approved'; points=80; events=3; action='two_factor_required'; expected='two_factor_required'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 3 | at-block-with-repeated-evidence | `original='approved'; points=80; events=4; action='rejected'; expected='rejected'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 4 | above-block | `original='approved'; points=81; events=4; action='rejected'; expected='rejected'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 5 | preserve-two-factor | `original='two_factor_required'; points=0; events=0; action='none'; expected='two_factor_required'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 6 | preserve-rejection-with-no-account-risk | `original='rejected'; points=0; events=0; action='none'; expected='rejected'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 7 | never-relax-rejection | `original='rejected'; points=40; events=2; action='two_factor_required'; expected='rejected'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |
| 8 | escalate-two-factor | `original='two_factor_required'; points=80; events=4; action='rejected'; expected='rejected'` | [P06](politicas-negocio.md#p06)<br>[P01](politicas-negocio.md#p01) |

<a id="suite-12"></a>

### 12. Expiração do acumulado no PostgreSQL

Fonte: [test_account_untrust_db.py](../tests/test_account_untrust_db.py). **1 funções / 1 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_account_untrust_db--test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts"></a>[`test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts`](../tests/test_account_untrust_db.py#L15) | PostgreSQL + controlador/repositório | Evidência com 23,99h entra; exatamente 24h, futura e de outra conta ficam fora. Após expirar a única evidência, o Pix normal volta a aprovar. Os 40 pontos inseridos são fixture de consulta, não incremento válido gerado pelo motor. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |

<a id="suite-13"></a>

### 13. Contrastes de causa e isolamento da suspeita própria

Fonte: [test_untrust_contrasts.py](../tests/test_untrust_contrasts.py). **7 funções / 16 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause"></a>[`test_same_request_different_context_has_a_specific_cause`](../tests/test_untrust_contrasts.py#L70) | Unitário | Mantém pedido igual e altera só referência, destino ou terceiro titular: confere score, decisão e incremento esperados em cada par; destino pode mudar a decisão sem virar evidência própria. | [P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[R07 — Destino desconhecido](politicas-negocio.md#r07)<br>[R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[R09 — Aparelho desconhecido](politicas-negocio.md#r09)<br>[R10 — Aparelho compartilhado](politicas-negocio.md#r10) |
| <a id="test_untrust_contrasts--test_identical_clean_pix_changes_only_because_of_accumulated_evidence"></a>[`test_identical_clean_pix_changes_only_because_of_accumulated_evidence`](../tests/test_untrust_contrasts.py#L85) | Unitário | Mesmo Pix com score zero aprova com histórico 39 e exige 2FA com 40; evidência transacional fica idêntica e incremento zero. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_untrust_contrasts--test_correlated_device_signals_accumulate_only_the_capped_contribution"></a>[`test_correlated_device_signals_accumulate_only_the_capped_contribution`](../tests/test_untrust_contrasts.py#L96) | Unitário | Aparelhos somam 70 brutos, teto efetivo 40 e incremento próprio 10; não usa soma bruta. | [P02 — Score e tetos](politicas-negocio.md#p02)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_untrust_contrasts--test_reclassifying_a_noneligible_rule_does_not_create_suspicion"></a>[`test_reclassifying_a_noneligible_rule_does_not_create_suspicion`](../tests/test_untrust_contrasts.py#L109) | Unitário | Remapear primeiro Pix, ausência de referência ou duplicidade para device não os torna elegíveis; incremento continua zero. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_untrust_contrasts--test_reclassifying_real_profile_evidence_does_not_erase_suspicion"></a>[`test_reclassifying_real_profile_evidence_does_not_erase_suspicion`](../tests/test_untrust_contrasts.py#L129) | Unitário | Mover perfil para exposure preserva score 80 e incremento 20; elegibilidade segue a natureza da regra. | [R08 — Desvio de perfil](politicas-negocio.md#r08)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_untrust_contrasts--test_temporal_observation_and_restriction_do_not_feed_own_increment"></a>[`test_temporal_observation_and_restriction_do_not_feed_own_increment`](../tests/test_untrust_contrasts.py#L147) | Unitário | Saída temporal 100 em off/shadow e restrição histórica 40 não tornam aparelho isolado de score 20 uma nova evidência própria. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_untrust_contrasts--test_irrelevant_request_changes_preserve_decision_and_suspicion"></a>[`test_irrelevant_request_changes_preserve_decision_and_suspicion`](../tests/test_untrust_contrasts.py#L163) | Unitário | Mantido o histórico, trocar ID, IP, geolocalização ou representação equivalente do fuso preserva decisão e suspeita; esses dados não são sinais adicionais no motor puro. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P10 — Contrato e validação](politicas-negocio.md#p10) |

**Casos individuais de `test_same_request_different_context_has_a_specific_cause` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | same-pix-profile-risk-with-or-without-second-factor | `left=NORMAL; right=replace(NORMAL, known_destination=False); amount=100000; expected_scores=(80, 95); expected_statuses=('two_factor_required', 'rejected'); expected_increments=(20, 20); changed_rule='unfamiliar_destination'` | [P01](politicas-negocio.md#p01)<br>[P06](politicas-negocio.md#p06)<br>[R07](politicas-negocio.md#r07)<br>[R08](politicas-negocio.md#r08)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10) |
| 2 | same-amount-different-customer-reference | `left=NORMAL; right=replace(NORMAL, profile_amount=30000); amount=50000; expected_scores=(0, 80); expected_statuses=('approved', 'two_factor_required'); expected_increments=(0, 20); changed_rule='amount_above_customer_profile'` | [P01](politicas-negocio.md#p01)<br>[P06](politicas-negocio.md#p06)<br>[R07](politicas-negocio.md#r07)<br>[R08](politicas-negocio.md#r08)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10) |
| 3 | new-device-alone-versus-new-device-and-recipient | `left=replace(NORMAL, known_device=False); right=replace(NORMAL, known_device=False, known_destination=False); amount=50000; expected_scores=(20, 35); expected_statuses=('approved', 'two_factor_required'); expected_increments=(0, 5); changed_rule='unfamiliar_destination'` | [P01](politicas-negocio.md#p01)<br>[P06](politicas-negocio.md#p06)<br>[R07](politicas-negocio.md#r07)<br>[R08](politicas-negocio.md#r08)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10) |
| 4 | shared-family-device-versus-third-owner | `left=replace(NORMAL, device_other_owners=1); right=replace(NORMAL, device_other_owners=2); amount=1000; expected_scores=(0, 30); expected_statuses=('approved', 'two_factor_required'); expected_increments=(0, 8); changed_rule='shared_device'` | [P01](politicas-negocio.md#p01)<br>[P06](politicas-negocio.md#p06)<br>[R07](politicas-negocio.md#r07)<br>[R08](politicas-negocio.md#r08)<br>[R09](politicas-negocio.md#r09)<br>[R10](politicas-negocio.md#r10) |

**Casos individuais de `test_reclassifying_a_noneligible_rule_does_not_create_suspicion` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_contrasts--test_reclassifying_a_noneligible_rule_does_not_create_suspicion). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `rule='first_transaction'` | [P06](politicas-negocio.md#p06)<br>[P04](politicas-negocio.md#p04) |
| 2 | — | `rule='insufficient_amount_history'` | [P06](politicas-negocio.md#p06)<br>[P04](politicas-negocio.md#p04) |
| 3 | — | `rule='possible_duplicate_payment'` | [P06](politicas-negocio.md#p06)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_temporal_observation_and_restriction_do_not_feed_own_increment` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_contrasts--test_temporal_observation_and_restriction_do_not_feed_own_increment). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `mode='off'` | [P06](politicas-negocio.md#p06)<br>[P09](politicas-negocio.md#p09) |
| 2 | — | `mode='shadow'` | [P06](politicas-negocio.md#p06)<br>[P09](politicas-negocio.md#p09) |

**Casos individuais de `test_irrelevant_request_changes_preserve_decision_and_suspicion` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_contrasts--test_irrelevant_request_changes_preserve_decision_and_suspicion). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `field='id'` | [P06](politicas-negocio.md#p06)<br>[P10](politicas-negocio.md#p10) |
| 2 | — | `field='ip'` | [P06](politicas-negocio.md#p06)<br>[P10](politicas-negocio.md#p10) |
| 3 | — | `field='geolocation'` | [P06](politicas-negocio.md#p06)<br>[P10](politicas-negocio.md#p10) |
| 4 | — | `field='equivalent_timezone'` | [P06](politicas-negocio.md#p06)<br>[P10](politicas-negocio.md#p10) |

<a id="suite-14"></a>

### 14. Equivalência entre replay offline e decisões persistidas

Fonte: [test_untrust_replay.py](../tests/test_untrust_replay.py). **3 funções / 16 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step"></a>[`test_replay_agrees_with_persisted_decisions_at_each_step`](../tests/test_untrust_replay.py#L88) | PostgreSQL + controlador/repositório | Em 13 cenários, compara cada passo do replay com controlador/PostgreSQL: duplicidade na fronteira, perfil, combinações, compartilhamento, expiração em 24h e idempotência; score, acumulado e metadados precisam coincidir. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[R13 — Possível duplicidade](politicas-negocio.md#r13)<br>[R08 — Desvio de perfil](politicas-negocio.md#r08) |
| <a id="test_untrust_replay--test_replay_rejects_conflicting_ids_instead_of_recounting_risk"></a>[`test_replay_rejects_conflicting_ids_instead_of_recounting_risk`](../tests/test_untrust_replay.py#L128) | Unitário | Mesmo ID com valor diferente gera TransactionConflict no simulador; não conta como nova evidência. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_untrust_replay--test_comparison_report_attributes_the_same_pix_change_to_its_account_history"></a>[`test_comparison_report_attributes_the_same_pix_change_to_its_account_history`](../tests/test_untrust_replay.py#L136) | Unitário | Para rótulo legítimo/fraude sintéticos, atribui approved→2FA ao acumulado 40, mantendo score transacional zero e incremento zero; separa fricção legítima de desafio em positivo. | [P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P14 — Validação experimental](politicas-negocio.md#p14) |

**Casos individuais de `test_replay_agrees_with_persisted_decisions_at_each_step` (13)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `scenario='duplicate-inside'; expected='two_factor_required'; score=30; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 2 | — | `scenario='duplicate-boundary'; expected='two_factor_required'; score=30; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 3 | — | `scenario='duplicate-outside'; expected='approved'; score=0; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 4 | — | `scenario='duplicate-same-time'; expected='two_factor_required'; score=30; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 5 | — | `scenario='profile-below'; expected='approved'; score=0; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 6 | — | `scenario='profile-at'; expected='two_factor_required'; score=80; account_score=20` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 7 | — | `scenario='profile-and-recipient'; expected='rejected'; score=95; account_score=20` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 8 | — | `scenario='device-and-recipient'; expected='two_factor_required'; score=35; account_score=5` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 9 | — | `scenario='shared-device'; expected='two_factor_required'; score=30; account_score=8` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 10 | — | `scenario='untrust-active'; expected='two_factor_required'; score=0; account_score=40` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 11 | — | `scenario='untrust-expired'; expected='approved'; score=0; account_score=20` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 12 | — | `scenario='untrust-outside'; expected='approved'; score=0; account_score=20` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |
| 13 | — | `scenario='idempotent'; expected='approved'; score=0; account_score=0` | [P11](politicas-negocio.md#p11)<br>[P03](politicas-negocio.md#p03)<br>[P06](politicas-negocio.md#p06)<br>[R13](politicas-negocio.md#r13)<br>[R08](politicas-negocio.md#r08) |

**Casos individuais de `test_comparison_report_attributes_the_same_pix_change_to_its_account_history` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_untrust_replay--test_comparison_report_attributes_the_same_pix_change_to_its_account_history). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `fraud=0; label='synthetic_legitimate'` | [P06](politicas-negocio.md#p06)<br>[P14](politicas-negocio.md#p14) |
| 2 | — | `fraud=1; label='synthetic_fraud'` | [P06](politicas-negocio.md#p06)<br>[P14](politicas-negocio.md#p14) |

<a id="suite-15"></a>

### 15. Titular, vínculos societários e ocorrências confirmadas

Fonte: [test_entity_risk.py](../tests/test_entity_risk.py). **20 funções / 28 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_entity_risk--test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct"></a>[`test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct`](../tests/test_entity_risk.py#L80) | Unitário | Dez empresas controladas com incidentes independentes geram exposição 100, mas suspeita própria zero; em contribute acrescenta 20 e exige 2FA sem alterar o objeto original. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_new_company_inherits_exposure_through_verified_common_controller"></a>[`test_new_company_inherits_exposure_through_verified_common_controller`](../tests/test_entity_risk.py#L97) | Unitário | Empresa recém-criada pode ter exposição pelos incidentes de outras controladas do mesmo controlador, sem herdar ocorrências próprias; caminhos têm duas arestas. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_multiple_company_levels_and_cycles_do_not_duplicate_events"></a>[`test_multiple_company_levels_and_cycles_do_not_duplicate_events`](../tests/test_entity_risk.py#L108) | Unitário | Estrutura com holding e ciclo encontra um incidente apenas, sem duplicá-lo por caminhos; uma ocorrência relacionada não basta para a ação por múltiplos incidentes. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_same_incident_across_ten_cnpjs_is_one_independent_evidence"></a>[`test_same_incident_across_ten_cnpjs_is_one_independent_evidence`](../tests/test_entity_risk.py#L121) | Unitário | Um incidente com dez CNPJs conta uma evidência; exposição 90, sem ação por multiplicidade. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_company_branches_are_one_company_root_not_ten_companies"></a>[`test_company_branches_are_one_company_root_not_ten_companies`](../tests/test_entity_risk.py#L130) | Unitário | Dez filiais de uma raiz contam uma empresa e um incidente; quantidade de estabelecimentos não infla corroboração. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override"></a>[`test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override`](../tests/test_entity_risk.py#L142) | Unitário | Contador/minoritário/administrador ficam em exposição máxima 0/18/45, sem incidentes fortes nem ação por múltiplas ocorrências. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud"></a>[`test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud`](../tests/test_entity_risk.py#L160) | Unitário | Vínculo não verificado, não conhecido, ainda não iniciado, encerrado ou iniciado depois da ocorrência não transmite o incidente. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_incident_must_be_known_active_and_not_revoked_at_decision"></a>[`test_incident_must_be_known_active_and_not_revoked_at_decision`](../tests/test_entity_risk.py#L174) | Unitário | Incidente conhecido no futuro, expirando no instante atual ou revogado nesse instante fica fora da avaliação. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation"></a>[`test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation`](../tests/test_entity_risk.py#L179) | Unitário | Ocorrência confirmada de 60 dias continua válida sem expiração/revogação; não segue a janela heurística de 24h. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores"></a>[`test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores`](../tests/test_entity_risk.py#L189) | Unitário | Duas contas com incrementos 20 somam 40 por titular, deduplicados por evento; exige 2FA em contribute sem pontos relacionais nem cadastro. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_entity_risk--test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded"></a>[`test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded`](../tests/test_entity_risk.py#L204) | Unitário | Incrementos exatamente em 24h e recebidos no futuro são excluídos; somente incremento atual 20 entra. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_entity_risk--test_rule_evidence_from_before_ownership_does_not_create_soft_exposure"></a>[`test_rule_evidence_from_before_ownership_does_not_create_soft_exposure`](../tests/test_entity_risk.py#L214) | Unitário | Suspeita de empresa anterior ao vínculo de controle não vira exposição indireta do novo controlador. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_clean_companies_do_not_dilute_high_risk_company"></a>[`test_clean_companies_do_not_dilute_high_risk_company`](../tests/test_entity_risk.py#L221) | Unitário | Uma empresa com ocorrência 90 mantém exposição 90 mesmo entre 49 empresas sem ocorrências; usa máximo, não média. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works"></a>[`test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works`](../tests/test_entity_risk.py#L227) | Unitário | Histórico próprio truncado resulta em score desconhecido/None; incidentes confirmados do cadastro ainda podem justificar 2FA. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence"></a>[`test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence`](../tests/test_entity_risk.py#L234) | Unitário | Cadastro de 120 empresas marca truncamento e suprime inferência relacionada; ocorrência diretamente no documento continua justificando 2FA. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_shadow_preserves_scores_decision_and_account_evidence"></a>[`test_shadow_preserves_scores_decision_and_account_evidence`](../tests/test_entity_risk.py#L245) | Unitário | Exposição calculada em shadow não modifica score, status, versão principal ou evidência original; applied_points zero. | [P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_entity_risk--test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence"></a>[`test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence`](../tests/test_entity_risk.py#L256) | Unitário | Em contribute, exposição ocupa apenas graph com teto 20; fator e contribuições reconciliam, sem criar dois fatores artificiais. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_entity_risk--test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved"></a>[`test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved`](../tests/test_entity_risk.py#L268) | Unitário | Peso graph zero impede pontos/2FA societário; decisão previamente rejeitada continua rejeitada. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_entity_risk--test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields"></a>[`test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields`](../tests/test_entity_risk.py#L277) | Unitário | Cadastro recusa documento mascarado, incidente duplicado, intervalo temporal invertido e campo extra. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_entity_risk--test_registry_loading_is_strict_hashed_and_off_is_explicit"></a>[`test_registry_loading_is_strict_hashed_and_off_is_explicit`](../tests/test_entity_risk.py#L288) | Unitário | Cadastro válido é carregado com hash; modo inválido e JSON incompatível falham; off retorna disabled. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P04 — Configuração do operador](politicas-negocio.md#p04)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

**Casos individuais de `test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_entity_risk--test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `role='accountant'; maximum=0` | [P07](politicas-negocio.md#p07) |
| 2 | — | `role='minority_partner'; maximum=18` | [P07](politicas-negocio.md#p07) |
| 3 | — | `role='administrator'; maximum=45` | [P07](politicas-negocio.md#p07) |

**Casos individuais de `test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_entity_risk--test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'verified': False}` | [P07](politicas-negocio.md#p07) |
| 2 | — | `changes={'known_at': NOW + timedelta(hours=1)}` | [P07](politicas-negocio.md#p07) |
| 3 | — | `changes={'valid_from': NOW + timedelta(hours=1)}` | [P07](politicas-negocio.md#p07) |
| 4 | — | `changes={'valid_until': NOW - timedelta(hours=1)}` | [P07](politicas-negocio.md#p07) |
| 5 | — | `changes={'valid_from': NOW - timedelta(days=1)}` | [P07](politicas-negocio.md#p07) |

**Casos individuais de `test_incident_must_be_known_active_and_not_revoked_at_decision` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_entity_risk--test_incident_must_be_known_active_and_not_revoked_at_decision). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `changes={'known_at': NOW + timedelta(hours=1)}` | [P07](politicas-negocio.md#p07) |
| 2 | — | `changes={'expires_at': NOW}` | [P07](politicas-negocio.md#p07) |
| 3 | — | `changes={'revoked_at': NOW}` | [P07](politicas-negocio.md#p07) |

<a id="suite-16"></a>

### 16. Histórico do titular e vínculos persistidos

Fonte: [test_entity_risk_db.py](../tests/test_entity_risk_db.py). **4 funções / 4 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_entity_risk_db--test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score"></a>[`test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score`](../tests/test_entity_risk_db.py#L55) | PostgreSQL + controlador/repositório | Consulta real agrega duas contas em 40, exclui incremento expirado/futuro e ignora exposição relacional armazenada; limite menor sinaliza incompletude. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_entity_risk_db--test_controller_new_account_preserves_own_titular_risk_and_saved_decision"></a>[`test_controller_new_account_preserves_own_titular_risk_and_saved_decision`](../tests/test_entity_risk_db.py#L77) | PostgreSQL + controlador/repositório | Nova conta mantém acumulado da conta zero, mas titular 40 exige 2FA em contribute; trocar serviço para off no replay preserva resultado e nenhum novo incremento é criado. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_entity_risk_db--test_postgres_payment_query_includes_receipts_and_bounds_history"></a>[`test_postgres_payment_query_includes_receipts_and_bounds_history`](../tests/test_entity_risk_db.py#L104) | PostgreSQL + controlador/repositório | Consulta pagamentos pelo destinatário encontra dois recebimentos; limit=1 sinaliza histórico incompleto. | [P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_entity_risk_db--test_confirmed_corporate_exposure_reaches_saved_controller_result"></a>[`test_confirmed_corporate_exposure_reaches_saved_controller_result`](../tests/test_entity_risk_db.py#L121) | PostgreSQL + controlador/repositório | Controlador com dez incidentes fortes recebe 2FA/score 20, mantendo conta e titular com suspeita própria zero e hash do cadastro salvo. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

<a id="suite-17"></a>

### 17. Indicadores direcionais de recebimentos e repasses

Fonte: [test_financial_features.py](../tests/test_financial_features.py). **4 funções / 4 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_financial_features--test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted"></a>[`test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted`](../tests/test_financial_features.py#L20) | Unitário | Receber de contato 90 difere de pagar a ele; entre nove saídas limpas o máximo segue 90 e proporção 10%; contribuição transacional continua zero. | [P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_financial_features--test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy"></a>[`test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy`](../tests/test_financial_features.py#L34) | Unitário | Duas entradas e saídas compatíveis geram dois pares apesar de IDs repetidos; recebimento pendente é apenas proxy de tentativa e cada entrada é consumida uma vez. | [P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_financial_features--test_future_old_rejected_and_self_transfers_do_not_create_exposure"></a>[`test_future_old_rejected_and_self_transfers_do_not_create_exposure`](../tests/test_financial_features.py#L49) | Unitário | Eventos futuros, >24h, rejeitados e para o próprio titular não criam contatos nem repasses. | [P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_financial_features--test_truncation_and_unknown_counterparty_risk_are_explicit"></a>[`test_truncation_and_unknown_counterparty_risk_are_explicit`](../tests/test_financial_features.py#L61) | Unitário | Contato sem risco conhecido aparece como desconhecido/None; truncamento retorna history_truncated sem métricas direcionais parciais. | [P08 — Indicadores financeiros](politicas-negocio.md#p08) |

<a id="suite-18"></a>

### 18. Grafo v2 na API: observação, relógios e falhas

Fonte: [test_temporal_live.py](../tests/test_temporal_live.py). **13 funções / 31 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_temporal_live--test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history"></a>[`test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history`](../tests/test_temporal_live.py#L37) | Unitário | Pix retrodatado usa três eventos já recebidos no instante real; produz score com cortes de evento e recepção separados, sem intervenção. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis"></a>[`test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis`](../tests/test_temporal_live.py#L50) | Unitário | Evento financeiro posterior ao candidato não entra como pagamento, mas seu incremento próprio já recebido entra uma vez e expira pelo relógio do servidor. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_temporal_live--test_missing_v2_model_has_explicit_zero_contribution"></a>[`test_missing_v2_model_has_explicit_zero_contribution`](../tests/test_temporal_live.py#L68) | Unitário | Arquivo ausente em off retorna disabled e em shadow unavailable; ambos sem score, pontos ou override. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_unvalidated_v2_contribution_cannot_be_enabled_accidentally"></a>[`test_unvalidated_v2_contribution_cannot_be_enabled_accidentally`](../tests/test_temporal_live.py#L78) | Unitário | contribute, on e erro de digitação são recusados; a integração permite somente off/shadow. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P04 — Configuração do operador](politicas-negocio.md#p04) |
| <a id="test_temporal_live--test_incomplete_neighborhood_abstains_without_calling_model"></a>[`test_incomplete_neighborhood_abstains_without_calling_model`](../tests/test_temporal_live.py#L86) | Unitário | Histórico, vizinhança ou evidência própria truncados e histórico inválido geram abstenção explícita sem chamar a inferência. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_invalid_prediction_does_not_escape_as_a_fraud_score"></a>[`test_invalid_prediction_does_not_escape_as_a_fraud_score`](../tests/test_temporal_live.py#L98) | Unitário | NaN, infinito e previsões fora de [0,1] viram inference_failed, score ausente e contribuição zero. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_high_v2_prediction_remains_observational"></a>[`test_high_v2_prediction_remains_observational`](../tests/test_temporal_live.py#L107) | Unitário | Previsão 1.0 é exibida internamente como 100, mas não acrescenta pontos nem altera decisão. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_http_v2_runs_by_default_and_saved_evidence_is_replayed"></a>[`test_http_v2_runs_by_default_and_saved_evidence_is_replayed`](../tests/test_temporal_live.py#L116) | HTTP + PostgreSQL | Três aprovações permitem score em shadow por HTTP; hash e política ficam salvos; GET/reenvio mantêm análise e incremento próprio zero. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_temporal_live--test_bad_model_json_is_unavailable_without_breaking_startup"></a>[`test_bad_model_json_is_unavailable_without_breaking_startup`](../tests/test_temporal_live.py#L134) | Unitário | Lista, null, texto e schema de arquitetura inválido tornam o modelo indisponível sem impedir a inicialização do serviço opcional. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions"></a>[`test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](../tests/test_temporal_live.py#L163) | Unitário | Mesmo com GNN=100 e pesos de exposição/atividade zero, piso de R$ 500 e limite forte de R$ 30 mil mantêm decisões obrigatórias; abaixo do piso aprova; grafo não interfere. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01)<br>[R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R04 — Referência insuficiente](politicas-negocio.md#r04)<br>[R02 — Montante](politicas-negocio.md#r02) |
| <a id="test_temporal_live--test_disabled_or_unavailable_model_does_not_query_optional_history"></a>[`test_disabled_or_unavailable_model_does_not_query_optional_history`](../tests/test_temporal_live.py#L190) | Unitário | Grafo off/ausente permite a decisão normal sem executar consulta opcional de vizinhança. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live--test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis"></a>[`test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis`](../tests/test_temporal_live.py#L197) | Unitário | OperationalError na consulta propaga e impede commit; falha de banco não pode ser disfarçada como sucesso da análise. Não testa aqui a conversão HTTP para 503. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_temporal_live--test_model_prediction_failure_cannot_modify_or_break_rule_decision"></a>[`test_model_prediction_failure_cannot_modify_or_break_rule_decision`](../tests/test_temporal_live.py#L205) | Unitário | ValueError de inferência preserva aprovação/score zero e incremento zero, registrando inference_failed. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |

**Casos individuais de `test_missing_v2_model_has_explicit_zero_contribution` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_missing_v2_model_has_explicit_zero_contribution). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `mode='off'; status='disabled'` | [P09](politicas-negocio.md#p09) |
| 2 | — | `mode='shadow'; status='unavailable'` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_unvalidated_v2_contribution_cannot_be_enabled_accidentally` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_unvalidated_v2_contribution_cannot_be_enabled_accidentally). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `mode='contribute'` | [P09](politicas-negocio.md#p09)<br>[P04](politicas-negocio.md#p04) |
| 2 | — | `mode='on'` | [P09](politicas-negocio.md#p09)<br>[P04](politicas-negocio.md#p04) |
| 3 | — | `mode='typo'` | [P09](politicas-negocio.md#p09)<br>[P04](politicas-negocio.md#p04) |

**Casos individuais de `test_incomplete_neighborhood_abstains_without_calling_model` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_incomplete_neighborhood_abstains_without_calling_model). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `reason='history_truncated'` | [P09](politicas-negocio.md#p09) |
| 2 | — | `reason='neighborhood_truncated'` | [P09](politicas-negocio.md#p09) |
| 3 | — | `reason='own_evidence_truncated'` | [P09](politicas-negocio.md#p09) |
| 4 | — | `reason='invalid_history'` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_invalid_prediction_does_not_escape_as_a_fraud_score` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_invalid_prediction_does_not_escape_as_a_fraud_score). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `value=float('nan')` | [P09](politicas-negocio.md#p09) |
| 2 | — | `value=float('inf')` | [P09](politicas-negocio.md#p09) |
| 3 | — | `value=-1` | [P09](politicas-negocio.md#p09) |
| 4 | — | `value=2` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_bad_model_json_is_unavailable_without_breaking_startup` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_bad_model_json_is_unavailable_without_breaking_startup). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `model_json='[]'` | [P09](politicas-negocio.md#p09) |
| 2 | — | `model_json='null'` | [P09](politicas-negocio.md#p09) |
| 3 | — | `model_json='"text"'` | [P09](politicas-negocio.md#p09) |
| 4 | — | `model_json='{"architecture":"invalid"}'` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions` (6)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `registered=0; amount=50000; expected='two_factor_required'; source='first_transaction'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 2 | — | `registered=2; amount=50000; expected='two_factor_required'; source='insufficient_history'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 3 | — | `registered=0; amount=49999; expected='approved'; source='risk_score'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 4 | — | `registered=2; amount=49999; expected='approved'; source='risk_score'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 5 | — | `registered=0; amount=3000000; expected='rejected'; source='hard_limit'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |
| 6 | — | `registered=2; amount=3000000; expected='rejected'; source='hard_limit'` | [P09](politicas-negocio.md#p09)<br>[P01](politicas-negocio.md#p01)<br>[R03](politicas-negocio.md#r03)<br>[R04](politicas-negocio.md#r04)<br>[R02](politicas-negocio.md#r02) |

**Casos individuais de `test_disabled_or_unavailable_model_does_not_query_optional_history` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live--test_disabled_or_unavailable_model_does_not_query_optional_history). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `mode='off'` | [P09](politicas-negocio.md#p09) |
| 2 | — | `mode='shadow'` | [P09](politicas-negocio.md#p09) |

<a id="suite-19"></a>

### 19. Recorte temporal real no PostgreSQL

Fonte: [test_temporal_live_db.py](../tests/test_temporal_live_db.py). **5 funções / 10 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_temporal_live_db--test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood"></a>[`test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood`](../tests/test_temporal_live_db.py#L61) | PostgreSQL + controlador/repositório | Consulta encontra entrada e remetente a dois saltos, busca incremento próprio separadamente e exclui pagamento alheio; evento próprio pode ter data financeira futura já recebido. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live_db--test_own_history_uses_received_window_and_rejects_legacy_evidence"></a>[`test_own_history_uses_received_window_and_rejects_legacy_evidence`](../tests/test_temporal_live_db.py#L98) | PostgreSQL + controlador/repositório | Para Pix retrodatado, evidência sender-evidence-v2 recebida há uma hora entra; exatamente 24h, recepção futura e versão legada ficam fora. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06) |
| <a id="test_temporal_live_db--test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample"></a>[`test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample`](../tests/test_temporal_live_db.py#L129) | PostgreSQL + controlador/repositório | Excede separadamente 300 pagamentos, 100 entidades e 300 evidências próprias; retorna o motivo de truncamento e nenhum score parcial. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live_db--test_legacy_payload_cannot_break_optional_v2_observation"></a>[`test_legacy_payload_cannot_break_optional_v2_observation`](../tests/test_temporal_live_db.py#L161) | PostgreSQL + controlador/repositório | Linha antiga com payload vazio provoca invalid_history na consulta; a observação não tenta inferir dados ausentes. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_live_db--test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay"></a>[`test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay`](../tests/test_temporal_live_db.py#L185) | PostgreSQL + controlador/repositório | Cruza controlador/contador com entity shadow/contribute: controlador tem exposição 95 e só contribute exige 2FA; contador 0. Suspeita própria permanece 0, v2 só observa e replay preserva decisão. | [P07 — Titular e vínculos](politicas-negocio.md#p07)<br>[P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |

**Casos individuais de `test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live_db--test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `reason='history_truncated'; count=301; old_event=False` | [P09](politicas-negocio.md#p09) |
| 2 | — | `reason='neighborhood_truncated'; count=100; old_event=False` | [P09](politicas-negocio.md#p09) |
| 3 | — | `reason='own_evidence_truncated'; count=301; old_event=True` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_live_db--test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `entity_mode='shadow'; role='controller'; exposure=95; action='two_factor_required'` | [P07](politicas-negocio.md#p07)<br>[P09](politicas-negocio.md#p09)<br>[P11](politicas-negocio.md#p11) |
| 2 | — | `entity_mode='shadow'; role='accountant'; exposure=0; action='none'` | [P07](politicas-negocio.md#p07)<br>[P09](politicas-negocio.md#p09)<br>[P11](politicas-negocio.md#p11) |
| 3 | — | `entity_mode='contribute'; role='controller'; exposure=95; action='two_factor_required'` | [P07](politicas-negocio.md#p07)<br>[P09](politicas-negocio.md#p09)<br>[P11](politicas-negocio.md#p11) |
| 4 | — | `entity_mode='contribute'; role='accountant'; exposure=0; action='none'` | [P07](politicas-negocio.md#p07)<br>[P09](politicas-negocio.md#p09)<br>[P11](politicas-negocio.md#p11) |

<a id="suite-20"></a>

### 20. Contrato HTTP do score temporal

Fonte: [test_gnn_http.py](../tests/test_gnn_http.py). **2 funções / 2 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_gnn_http--test_shadow_v2_assessment_is_saved_and_replayed"></a>[`test_shadow_v2_assessment_is_saved_and_replayed`](../tests/test_gnn_http.py#L9) | HTTP + PostgreSQL | Histórico sintético produz score v2 entre 0 e 100 em shadow; resposta pública usa untrust_score, detalhes só acrescentam aliases e GET/reenvio preservam a avaliação. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_gnn_http--test_future_cross_payer_history_cannot_influence_graph"></a>[`test_future_cross_payer_history_cannot_influence_graph`](../tests/test_gnn_http.py#L38) | HTTP + PostgreSQL | Evento futuro de outro pagador não afeta o candidato; vizinhança fica sem histórico elegível e retorna insufficient_history. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |

<a id="suite-21"></a>

### 21. Caso demonstrativo temporal reproduzível

Fonte: [test_temporal_case.py](../tests/test_temporal_case.py). **2 funções / 2 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_temporal_case--test_export_contains_actual_nodes_edges_and_all_rule_results"></a>[`test_export_contains_actual_nodes_edges_and_all_rule_results`](../tests/test_temporal_case.py#L21) | Offline / artefato sintético | Exportação offline contém 21 nós, seis tipos de aresta,13 regras avaliadas, duas ativas e 25 pontos; caso rápido tem 2 pares, lento 0, e previsão maior no rápido. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P14 — Validação experimental](politicas-negocio.md#p14)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_temporal_case--test_v2_case_runs_through_database_decision_and_replay"></a>[`test_v2_case_runs_through_database_decision_and_replay`](../tests/test_temporal_case.py#L41) | PostgreSQL + controlador/repositório | Caso real via SQL seleciona 14 eventos/18 nós, score do grafo≈97,3076; decisão continua approved/score 25, incremento próprio 0, com GET/replay idênticos. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[P14 — Validação experimental](politicas-negocio.md#p14) |

<a id="suite-22"></a>

### 22. Modelo temporal offline e integridade do treinamento

Fonte: [test_temporal_gnn.py](../tests/test_temporal_gnn.py). **17 funções / 29 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_temporal_gnn--test_payment_and_device_relations_are_separate_and_directional"></a>[`test_payment_and_device_relations_are_separate_and_directional`](../tests/test_temporal_gnn.py#L63) | Offline / artefato sintético | Confere paid_to/received_from, uses_device/used_by e owns/owned_by; relações inversas ocupam canais distintos. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_gnn--test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect"></a>[`test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect`](../tests/test_temporal_gnn.py#L76) | Offline / artefato sintético | Contato com suspeita 40 alimenta máximo de entrada ou saída conforme a direção, sem misturar os dois atributos. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_temporal_gnn--test_holder_identity_deduplicates_accounts_on_a_shared_device"></a>[`test_holder_identity_deduplicates_accounts_on_a_shared_device`](../tests/test_temporal_gnn.py#L88) | Offline / artefato sintético | Duas contas do mesmo titular no aparelho contam uma pessoa; novo titular aumenta a contagem de 1 para 2. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[R10 — Aparelho compartilhado](politicas-negocio.md#r10) |
| <a id="test_temporal_gnn--test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window"></a>[`test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window`](../tests/test_temporal_gnn.py#L102) | Offline / artefato sintético | Diferenças de 29,999 e 30 minutos formam par;30,001 e simultaneidade não formam. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_temporal_gnn--test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass"></a>[`test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass`](../tests/test_temporal_gnn.py#L109) | Offline / artefato sintético | Uma entrada sustenta um par apenas; saída posterior para suspeito sem entrada compatível não vira repasse suspeito. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P08 — Indicadores financeiros](politicas-negocio.md#p08) |
| <a id="test_temporal_gnn--test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact"></a>[`test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact`](../tests/test_temporal_gnn.py#L126) | Offline / artefato sintético | Mensagem de peso 0,5 vale metade da mensagem de peso 1 mesmo com vizinho único; agregação não cancela o decaimento. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_gnn--test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak"></a>[`test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak`](../tests/test_temporal_gnn.py#L134) | Offline / artefato sintético | Deduplica evento, ignora recepção futura, expira evidência em 24h e não usa rótulo/score/exposição inseridos no payload para alterar atributos. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge"></a>[`test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge`](../tests/test_temporal_gnn.py#L153) | Offline / artefato sintético | Rejeição com incremento 25 preserva evidência própria, mas não conta como histórico não rejeitado nem cria aresta financeira adicional. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_gnn--test_truncated_conflicting_and_unbounded_history_are_refused"></a>[`test_truncated_conflicting_and_unbounded_history_are_refused`](../tests/test_temporal_gnn.py#L162) | Offline / artefato sintético | Recusa histórico incompleto, incremento 26, IDs históricos conflitantes e 301 eventos. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_gnn--test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction"></a>[`test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction`](../tests/test_temporal_gnn.py#L175) | Offline / artefato sintético | Mantidos os cenários pareados, fluxo rápido tem ≥2 pares e previsão maior que o lento, que tem 0 pares; comprova sensibilidade temporal no exemplo sintético. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_synthetic_split_dates_and_openings_are_valid"></a>[`test_synthetic_split_dates_and_openings_are_valid`](../tests/test_temporal_gnn.py#L185) | Offline / artefato sintético | Treino/validação/teste usam janeiro/maio/setembro; abertura de toda conta precede a transação e não há campo auxiliar de abertura no payload. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_exported_v2_is_safe_finite_and_permutation_invariant"></a>[`test_exported_v2_is_safe_finite_and_permutation_invariant`](../tests/test_temporal_gnn.py#L195) | Offline / artefato sintético | Para sementes 42/43/44, previsão fica em [0,1], preserva valor ao reordenar eventos e ignora rótulo artificial adicionado ao candidato. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_comparison_selects_on_validation_and_records_parity_for_every_seed"></a>[`test_comparison_selects_on_validation_and_records_parity_for_every_seed`](../tests/test_temporal_gnn.py#L207) | Offline / artefato sintético | Artefato contém seis execuções tabular/v2 em três sementes; limiar do teste é o da validação, respeita orçamento na validação e exportação NumPy diverge <1e-5 do treino. É inspeção do relatório salvo. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics"></a>[`test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics`](../tests/test_temporal_gnn.py#L228) | Offline / artefato sintético | Recusa pesos NaN, dimensão incorreta, ordem de atributos incompatível e alvo de treinamento diferente. | [P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_temporal_gnn--test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget"></a>[`test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget`](../tests/test_temporal_gnn.py#L245) | Offline / artefato sintético | Scores constantes 0/0,5/1 em float32 permitem limiar de abstenção que não alerta nenhum caso com orçamento de falsos positivos zero. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_threshold_does_not_split_tied_legitimate_and_fraud_scores"></a>[`test_threshold_does_not_split_tied_legitimate_and_fraud_scores`](../tests/test_temporal_gnn.py#L251) | Offline / artefato sintético | Com empate em 0,8 entre classes, limiar 0,9 preserva orçamentozero; não separa artificialmente valores iguais. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_temporal_gnn--test_entity_identities_do_not_overlap_across_training_validation_and_test"></a>[`test_entity_identities_do_not_overlap_across_training_validation_and_test`](../tests/test_temporal_gnn.py#L257) | Offline / artefato sintético | Documentos de treino, validação e teste são disjuntos; evita vazamento da identidade entre partições. | [P14 — Validação experimental](politicas-negocio.md#p14) |

**Casos individuais de `test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_gnn--test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `minutes=29.999; expected=0.25` | [P09](politicas-negocio.md#p09)<br>[P08](politicas-negocio.md#p08) |
| 2 | — | `minutes=30; expected=0.25` | [P09](politicas-negocio.md#p09)<br>[P08](politicas-negocio.md#p08) |
| 3 | — | `minutes=30.001; expected=0` | [P09](politicas-negocio.md#p09)<br>[P08](politicas-negocio.md#p08) |
| 4 | — | `minutes=0; expected=0` | [P09](politicas-negocio.md#p09)<br>[P08](politicas-negocio.md#p08) |

**Casos individuais de `test_synthetic_split_dates_and_openings_are_valid` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_gnn--test_synthetic_split_dates_and_openings_are_valid). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `split='train'; month=1` | [P14](politicas-negocio.md#p14) |
| 2 | — | `split='validation'; month=5` | [P14](politicas-negocio.md#p14) |
| 3 | — | `split='test'; month=9` | [P14](politicas-negocio.md#p14) |

**Casos individuais de `test_exported_v2_is_safe_finite_and_permutation_invariant` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_gnn--test_exported_v2_is_safe_finite_and_permutation_invariant). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `seed=42` | [P09](politicas-negocio.md#p09)<br>[P14](politicas-negocio.md#p14) |
| 2 | — | `seed=43` | [P09](politicas-negocio.md#p09)<br>[P14](politicas-negocio.md#p14) |
| 3 | — | `seed=44` | [P09](politicas-negocio.md#p09)<br>[P14](politicas-negocio.md#p14) |

**Casos individuais de `test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_gnn--test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `change='nan_weight'` | [P09](politicas-negocio.md#p09) |
| 2 | — | `change='wrong_shape'` | [P09](politicas-negocio.md#p09) |
| 3 | — | `change='node_schema'` | [P09](politicas-negocio.md#p09) |
| 4 | — | `change='label_target'` | [P09](politicas-negocio.md#p09) |

**Casos individuais de `test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_temporal_gnn--test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `score=0` | [P14](politicas-negocio.md#p14) |
| 2 | — | `score=0.5` | [P14](politicas-negocio.md#p14) |
| 3 | — | `score=1` | [P14](politicas-negocio.md#p14) |

<a id="suite-23"></a>

### 23. Experimento heurístico de grafo offline

Fonte: [test_graph_untrust_experiment.py](../tests/test_graph_untrust_experiment.py). **10 funções / 27 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_graph_untrust_experiment--test_two_hops_finds_independent_evidence_without_counting_paths_or_root"></a>[`test_two_hops_finds_independent_evidence_without_counting_paths_or_root`](../tests/test_graph_untrust_experiment.py#L64) | Offline / artefato sintético | Dois saltos encontram um suspeito; um salto não. Caminhos repetidos e evidência da raiz não contam como novas entidades suspeitas. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_future_and_expired_evidence_do_not_increase_current_risk"></a>[`test_future_and_expired_evidence_do_not_increase_current_risk`](../tests/test_graph_untrust_experiment.py#L78) | Offline / artefato sintético | Evidência futura/>24h e conexão financeira antiga não aumentam o sinal heurístico atual. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy"></a>[`test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy`](../tests/test_graph_untrust_experiment.py#L86) | Offline / artefato sintético | Rejeição não conecta pagador a suspeito; pendência conecta como proxy de tentativa, sem comprovar liquidação. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages"></a>[`test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages`](../tests/test_graph_untrust_experiment.py#L92) | Offline / artefato sintético | Neste experimento, contatos limpos e conexões antigas reduzem weighted_neighbors. Essa diluição não é a política de máximo societário de entity_risk. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_neighbor_budget_keeps_latest_contacts_and_bounds_search"></a>[`test_neighbor_budget_keeps_latest_contacts_and_bounds_search`](../tests/test_graph_untrust_experiment.py#L100) | Offline / artefato sintético | Limita aos dez contatos mais recentes por expansão; suspeito antigo fora do orçamento não entra; visita no máximo 1+10+100 nós. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_repass_requires_distinct_receipts_time_order_value_and_different_destination"></a>[`test_repass_requires_distinct_receipts_time_order_value_and_different_destination`](../tests/test_graph_untrust_experiment.py#L109) | Offline / artefato sintético | Uma entrada não suporta duas saídas; segunda entrada permite outro par; devolução ao remetente e saída tardia não contam. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_replay_deduplicates_retries_and_excludes_future_and_candidate"></a>[`test_replay_deduplicates_retries_and_excludes_future_and_candidate`](../tests/test_graph_untrust_experiment.py#L125) | Offline / artefato sintético | Duplicar registros, incluir futuro e candidato não modifica histórico, incrementos, decisão ou metadados do replay. | [P14 — Validação experimental](politicas-negocio.md#p14)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_graph_untrust_experiment--test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate"></a>[`test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate`](../tests/test_graph_untrust_experiment.py#L139) | Offline / artefato sintético | Simulador soma 5 ao score 25 e propõe 2FA em 30; preserva rejeição/2FA anteriores e não muta a linha de base. Não ativa contribuição na API. | [P14 — Validação experimental](politicas-negocio.md#p14)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_graph_untrust_experiment--test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint"></a>[`test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint`](../tests/test_graph_untrust_experiment.py#L149) | Offline / artefato sintético | Gerador atribui intenção distinta a mula e comerciante, é determinístico pela semente e separa identidade entre validação e teste. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_graph_untrust_experiment--test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly"></a>[`test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly`](../tests/test_graph_untrust_experiment.py#L160) | Offline / artefato sintético | Cruza todas as categorias STRESS_KINDS e sementes 20000/20001; candidatos continuam aprovados com score 0/25 para isolar o efeito relacional experimental. | [P14 — Validação experimental](politicas-negocio.md#p14) |

**Casos individuais de `test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly` (18)**

Todos verificam o cenário e as políticas da [análise da função](#test_graph_untrust_experiment--test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `seed=20000; expected_score=0; kind='mule_direct'` | [P14](politicas-negocio.md#p14) |
| 2 | — | `seed=20000; expected_score=0; kind='mule_two_hops'` | [P14](politicas-negocio.md#p14) |
| 3 | — | `seed=20000; expected_score=0; kind='mule_no_risky_neighbor'` | [P14](politicas-negocio.md#p14) |
| 4 | — | `seed=20000; expected_score=0; kind='mule_first_repass'` | [P14](politicas-negocio.md#p14) |
| 5 | — | `seed=20000; expected_score=0; kind='innocent_payer'` | [P14](politicas-negocio.md#p14) |
| 6 | — | `seed=20000; expected_score=0; kind='merchant'` | [P14](politicas-negocio.md#p14) |
| 7 | — | `seed=20000; expected_score=0; kind='merchant_fast_settlement'` | [P14](politicas-negocio.md#p14) |
| 8 | — | `seed=20000; expected_score=0; kind='normal'` | [P14](politicas-negocio.md#p14) |
| 9 | — | `seed=20000; expected_score=0; kind='stale_contact'` | [P14](politicas-negocio.md#p14) |
| 10 | — | `seed=20001; expected_score=25; kind='mule_direct'` | [P14](politicas-negocio.md#p14) |
| 11 | — | `seed=20001; expected_score=25; kind='mule_two_hops'` | [P14](politicas-negocio.md#p14) |
| 12 | — | `seed=20001; expected_score=25; kind='mule_no_risky_neighbor'` | [P14](politicas-negocio.md#p14) |
| 13 | — | `seed=20001; expected_score=25; kind='mule_first_repass'` | [P14](politicas-negocio.md#p14) |
| 14 | — | `seed=20001; expected_score=25; kind='innocent_payer'` | [P14](politicas-negocio.md#p14) |
| 15 | — | `seed=20001; expected_score=25; kind='merchant'` | [P14](politicas-negocio.md#p14) |
| 16 | — | `seed=20001; expected_score=25; kind='merchant_fast_settlement'` | [P14](politicas-negocio.md#p14) |
| 17 | — | `seed=20001; expected_score=25; kind='normal'` | [P14](politicas-negocio.md#p14) |
| 18 | — | `seed=20001; expected_score=25; kind='stale_contact'` | [P14](politicas-negocio.md#p14) |

<a id="suite-24"></a>

### 24. Propostas experimentais de 2FA e controle de falsos positivos

Fonte: [test_gnn_validation.py](../tests/test_gnn_validation.py). **10 funções / 19 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_gnn_validation--test_candidate_never_relaxes_or_escalates_an_existing_intervention"></a>[`test_candidate_never_relaxes_or_escalates_an_existing_intervention`](../tests/test_gnn_validation.py#L44) | Offline / artefato sintético | Nas propostas score_only_2fa/corroborated_2fa, decisões já em 2FA ou rejeitadas permanecem iguais mesmo com score 100. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs"></a>[`test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs`](../tests/test_gnn_validation.py#L59) | Offline / artefato sintético | Com limiar 0,9, somente score disponível≥90, valor≥R$ 500 e≥2 pares rápidos permitem approved→2FA; score 89, ausência de score, valor 499,99 ou um par não intervêm. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score"></a>[`test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score`](../tests/test_gnn_validation.py#L68) | Offline / artefato sintético | Score ausente não intervém nem com limiarzero; score numéricozero é válido e satisfaz limiarzero na proposta baseada só em score. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases"></a>[`test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases`](../tests/test_gnn_validation.py#L73) | Offline / artefato sintético | Acrescentar 100 legítimos já em 2FA não reduz artificialmente a fricção entre aprováveis; limiar selecionado 0,95 evita novos desafios legítimos no exemplo. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_calibration_without_both_classes_disables_proposals"></a>[`test_calibration_without_both_classes_disables_proposals`](../tests/test_gnn_validation.py#L82) | Offline / artefato sintético | Calibração só com legítimos ou só com positivos escolhe limiar>1 e desativa propostas em vez de inventar calibração. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_report_separates_false_alarm_rate_from_incremental_legitimate_friction"></a>[`test_report_separates_false_alarm_rate_from_incremental_legitimate_friction`](../tests/test_gnn_validation.py#L88) | Offline / artefato sintético | Exemplo distingue FPR 1/120 de fricção adicional 1/100, contabiliza 8 novos desafios em positivos e zero rejeições; intervalo superior não passa orçamento 1%. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget"></a>[`test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget`](../tests/test_gnn_validation.py#L102) | Offline / artefato sintético | Wilson 95% trata amostra vazia como[0,1]; zero em 10 não comprova limite 1%, zero em 600 satisfaz,6/600 não satisfaz pelo limite superior; contagem impossível é recusada. | [P14 — Validação experimental](politicas-negocio.md#p14) |
| <a id="test_gnn_validation--test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account"></a>[`test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account`](../tests/test_gnn_validation.py#L111) | Offline / artefato sintético | Casos do contrato preservam Pix de R$ 1.500 e conta 88213, histórico anterior válido e primeiro caso sem histórico; somente último cenário tem intenção sintética positiva. | [P14 — Validação experimental](politicas-negocio.md#p14)<br>[P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_gnn_validation--test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow"></a>[`test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow`](../tests/test_gnn_validation.py#L125) | PostgreSQL + controlador/repositório | Cenário de repasse rápido legítimo do contrato gera GNN > 99, mas permanece aprovado com score transacional e incremento próprios zero; GET/reenvio preservam resultado e a transação externa é descartada. | [P09 — Grafo temporal v2](politicas-negocio.md#p09)<br>[P14 — Validação experimental](politicas-negocio.md#p14)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_gnn_validation--test_validation_uses_real_sql_without_persisting_synthetic_scenarios"></a>[`test_validation_uses_real_sql_without_persisting_synthetic_scenarios`](../tests/test_gnn_validation.py#L163) | PostgreSQL + controlador/repositório | Casos temporal_fast e merchant_fast_settlement usam controlador/SQL reais, geram score válido no recorte e mantêm a contagem de linhas após rollback externo. | [P14 — Validação experimental](politicas-negocio.md#p14)<br>[P09 — Grafo temporal v2](politicas-negocio.md#p09) |

**Casos individuais de `test_candidate_never_relaxes_or_escalates_an_existing_intervention` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_gnn_validation--test_candidate_never_relaxes_or_escalates_an_existing_intervention). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `method='score_only_2fa'; status='two_factor_required'` | [P14](politicas-negocio.md#p14) |
| 2 | — | `method='score_only_2fa'; status='rejected'` | [P14](politicas-negocio.md#p14) |
| 3 | — | `method='corroborated_2fa'; status='two_factor_required'` | [P14](politicas-negocio.md#p14) |
| 4 | — | `method='corroborated_2fa'; status='rejected'` | [P14](politicas-negocio.md#p14) |

**Casos individuais de `test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs` (5)**

Todos verificam o cenário e as políticas da [análise da função](#test_gnn_validation--test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `score=100; amount=49999; pairs=2; expected='approved'` | [P14](politicas-negocio.md#p14) |
| 2 | — | `score=100; amount=50000; pairs=1; expected='approved'` | [P14](politicas-negocio.md#p14) |
| 3 | — | `score=100; amount=50000; pairs=2; expected='two_factor_required'` | [P14](politicas-negocio.md#p14) |
| 4 | — | `score=89; amount=50000; pairs=2; expected='approved'` | [P14](politicas-negocio.md#p14) |
| 5 | — | `score=None; amount=50000; pairs=2; expected='approved'` | [P14](politicas-negocio.md#p14) |

**Casos individuais de `test_calibration_without_both_classes_disables_proposals` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_gnn_validation--test_calibration_without_both_classes_disables_proposals). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `label=0` | [P14](politicas-negocio.md#p14) |
| 2 | — | `label=1` | [P14](politicas-negocio.md#p14) |

**Casos individuais de `test_validation_uses_real_sql_without_persisting_synthetic_scenarios` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_gnn_validation--test_validation_uses_real_sql_without_persisting_synthetic_scenarios). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `kind='temporal_fast'` | [P14](politicas-negocio.md#p14)<br>[P09](politicas-negocio.md#p09) |
| 2 | — | `kind='merchant_fast_settlement'` | [P14](politicas-negocio.md#p14)<br>[P09](politicas-negocio.md#p09) |

<a id="suite-25"></a>

### 25. Contrato HTTP, histórico e concorrência

Fonte: [test_pix.py](../tests/test_pix.py). **19 funções / 43 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_pix--test_all_reasons_and_rejection_priority"></a>[`test_all_reasons_and_rejection_priority`](../tests/test_pix.py#L11) | HTTP + PostgreSQL | Pix de R$ 30mil em conta nova registra montante forte, primeiro Pix e conta nova; rejeição forte prevalece e todas as causas acionadas ficam salvas. | [R02 — Montante](politicas-negocio.md#r02)<br>[R03 — Primeiro Pix](politicas-negocio.md#r03)<br>[R05 — Origem recente](politicas-negocio.md#r05)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_pix--test_sixth_attempt_is_rejected_and_rejections_are_saved"></a>[`test_sixth_attempt_is_rejected_and_rejections_are_saved`](../tests/test_pix.py#L23) | HTTP + PostgreSQL | Cinco tentativas aprovam; sexta rejeita e é consultável; tentativa posterior enxerga também a rejeição na contagem. | [R01 — Frequência](politicas-negocio.md#r01)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_pix--test_retries_do_not_inflate_velocity"></a>[`test_retries_do_not_inflate_velocity`](../tests/test_pix.py#L35) | HTTP + PostgreSQL | Sete reenvios do mesmo ID retornam original; próximo ID vê apenas uma tentativa anterior. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11)<br>[R01 — Frequência](politicas-negocio.md#r01) |
| <a id="test_pix--test_changed_payload_conflicts_and_preserves_original"></a>[`test_changed_payload_conflicts_and_preserves_original`](../tests/test_pix.py#L42) | HTTP + PostgreSQL | Alterar um centavo no mesmo ID gera 409, mantém decisão original e não acrescenta tentativa ao histórico. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_pix--test_equivalent_timezone_and_document_format_replay"></a>[`test_equivalent_timezone_and_document_format_replay`](../tests/test_pix.py#L53) | HTTP + PostgreSQL | CPF pontuado/dígitos e instante equivalente emUTC/-03 são normalizados para o mesmo conteúdo e reproduzem a análise. | [P10 — Contrato e validação](politicas-negocio.md#p10)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_pix--test_velocity_window_and_future_history"></a>[`test_velocity_window_and_future_history`](../tests/test_pix.py#L65) | HTTP + PostgreSQL | Evento exatamente 600s antes entra;601s e evento futuro não entram na frequência. | [R01 — Frequência](politicas-negocio.md#r01)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_pix--test_accumulated_value_boundary"></a>[`test_accumulated_value_boundary`](../tests/test_pix.py#L71) | HTTP + PostgreSQL | Duas tentativas de R$ 15mil atingem exatamenteR$ 30mil; a segunda rejeita por montante. | [R02 — Montante](politicas-negocio.md#r02) |
| <a id="test_pix--test_new_destination_scores_only_above_minimum"></a>[`test_new_destination_scores_only_above_minimum`](../tests/test_pix.py#L78) | HTTP + PostgreSQL | Destino novo abaixo de R$ 500 não pontua; outro destino novo a R$ 500 soma 15 e ainda aprova com referência formada. | [R06 — Destino recente](politicas-negocio.md#r06) |
| <a id="test_pix--test_missing_geolocation_is_valid"></a>[`test_missing_geolocation_is_valid`](../tests/test_pix.py#L91) | HTTP + PostgreSQL | Remover geolocalização mantém pedido válido/aprovado; o campo é opcional. | [P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_pix--test_cnpj_is_valid"></a>[`test_cnpj_is_valid`](../tests/test_pix.py#L96) | HTTP + PostgreSQL | Documento de 14 dígitos é aceito para titular; valida formato, sem demonstrar verificação cadastral ou dígito verificador. | [P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_pix--test_invalid_payload_is_rejected_without_consuming_id"></a>[`test_invalid_payload_is_rejected_without_consuming_id`](../tests/test_pix.py#L128) | HTTP + PostgreSQL | As 22 mutações inválidas discriminadas abaixo retornam 400 no envelope padrão, GET 404 e permitem reaproveitar o ID com conteúdo corrigido. | [P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_pix--test_required_and_unknown_fields"></a>[`test_required_and_unknown_fields`](../tests/test_pix.py#L141) | HTTP + PostgreSQL | Campo extra e ausência do participante do destino retornam 400. | [P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_pix--test_missing_transaction"></a>[`test_missing_transaction`](../tests/test_pix.py#L149) | HTTP + PostgreSQL | Consulta a ID inexistente retorna 404. | [P10 — Contrato e validação](politicas-negocio.md#p10) |
| <a id="test_pix--test_business_endpoints_accept_requests_without_internal_token"></a>[`test_business_endpoints_accept_requests_without_internal_token`](../tests/test_pix.py#L154) | HTTP + PostgreSQL | POST/GET funcionam sem token ou com token incorreto; o contrato não exige autenticação por INTERNAL-TOKEN. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_pix--test_public_health_and_openapi"></a>[`test_public_health_and_openapi`](../tests/test_pix.py#L160) | HTTP + PostgreSQL | health retorna 200/ok; health_check e ready retornam 204; OpenAPI lista Pix sem esquema/exigência de autenticação. Exercita disponibilidade positiva, não indisponibilidade do banco. | [P10 — Contrato e validação](politicas-negocio.md#p10)<br>[P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_pix--test_concurrent_retries_share_one_analysis"></a>[`test_concurrent_retries_share_one_analysis`](../tests/test_pix.py#L172) | HTTP + PostgreSQL | Seis reenvios simultâneos retornam a mesma análise e contam uma tentativa. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_pix--test_concurrent_distinct_pix_cannot_bypass_velocity"></a>[`test_concurrent_distinct_pix_cannot_bypass_velocity`](../tests/test_pix.py#L179) | HTTP + PostgreSQL | Seis IDs concorrentes resultam em cinco aprovações e uma rejeição, sem ultrapassar o limite por corrida. | [R01 — Frequência](politicas-negocio.md#r01)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_pix--test_same_id_different_payers_cannot_overwrite"></a>[`test_same_id_different_payers_cannot_overwrite`](../tests/test_pix.py#L188) | HTTP + PostgreSQL | Dois pagadores concorrentes com mesmo ID produzem 200 e 409; um não sobrescreve o outro. | [P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_pix--test_velocity_is_shared_by_payer_across_accounts"></a>[`test_velocity_is_shared_by_payer_across_accounts`](../tests/test_pix.py#L196) | HTTP + PostgreSQL | Cinco tentativas em contas distintas do mesmo documento fazem a seguinte rejeitar; frequência é por pagador. | [R01 — Frequência](politicas-negocio.md#r01)<br>[P03 — Históricos elegíveis](politicas-negocio.md#p03) |

**Casos individuais de `test_velocity_window_and_future_history` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_pix--test_velocity_window_and_future_history). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `seconds=600; expected_count=1` | [R01](politicas-negocio.md#r01)<br>[P03](politicas-negocio.md#p03) |
| 2 | — | `seconds=601; expected_count=0` | [R01](politicas-negocio.md#r01)<br>[P03](politicas-negocio.md#p03) |
| 3 | — | `seconds=-1; expected_count=0` | [R01](politicas-negocio.md#r01)<br>[P03](politicas-negocio.md#p03) |

**Casos individuais de `test_invalid_payload_is_rejected_without_consuming_id` (22)**

Todos verificam o cenário e as políticas da [análise da função](#test_pix--test_invalid_payload_is_rejected_without_consuming_id). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `path=('amount',); value=0` | [P10](politicas-negocio.md#p10) |
| 2 | — | `path=('amount',); value=-1` | [P10](politicas-negocio.md#p10) |
| 3 | — | `path=('amount',); value=1.5` | [P10](politicas-negocio.md#p10) |
| 4 | — | `path=('amount',); value=1000.0` | [P10](politicas-negocio.md#p10) |
| 5 | — | `path=('amount',); value='1000'` | [P10](politicas-negocio.md#p10) |
| 6 | — | `path=('amount',); value=True` | [P10](politicas-negocio.md#p10) |
| 7 | — | `path=('amount',); value=9223372036854775808` | [P10](politicas-negocio.md#p10) |
| 8 | — | `path=('transaction_date',); value='2026-10-17T14:00:00'` | [P10](politicas-negocio.md#p10) |
| 9 | — | `path=('transaction_date',); value='invalid'` | [P10](politicas-negocio.md#p10) |
| 10 | — | `path=('id',); value=''` | [P10](politicas-negocio.md#p10) |
| 11 | — | `path=('id',); value='a/b'` | [P10](politicas-negocio.md#p10) |
| 12 | — | `path=('transaction_date',); value=1792243200` | [P10](politicas-negocio.md#p10) |
| 13 | — | `path=('source_account', 'opening_date'); value='2026-10-18T14:00:00Z'` | [P10](politicas-negocio.md#p10) |
| 14 | — | `path=('destination_account', 'opening_date'); value='2026-10-18T14:00:00Z'` | [P10](politicas-negocio.md#p10) |
| 15 | — | `path=('source_account', 'owner', 'document_number'); value='abc'` | [P10](politicas-negocio.md#p10) |
| 16 | — | `path=('source', 'ip'); value='not-an-ip'` | [P10](politicas-negocio.md#p10) |
| 17 | — | `path=('source', 'device_id'); value='   '` | [P10](politicas-negocio.md#p10) |
| 18 | — | `path=('source', 'geolocation', 'latitude'); value=91` | [P10](politicas-negocio.md#p10) |
| 19 | — | `path=('source', 'geolocation', 'longitude'); value=-181` | [P10](politicas-negocio.md#p10) |
| 20 | — | `path=('source', 'geolocation', 'latitude'); value='-23.56'` | [P10](politicas-negocio.md#p10) |
| 21 | — | `path=('destination_account', 'participant'); value=None` | [P10](politicas-negocio.md#p10) |
| 22 | — | `path=('destination_account', 'participant'); value='123'` | [P10](politicas-negocio.md#p10) |

**Casos individuais de `test_business_endpoints_accept_requests_without_internal_token` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_pix--test_business_endpoints_accept_requests_without_internal_token). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `token=None` | [P13](politicas-negocio.md#p13) |
| 2 | — | `token='wrong-token'` | [P13](politicas-negocio.md#p13) |

<a id="suite-26"></a>

### 26. Proteções de transporte e erros

Fonte: [test_api_security.py](../tests/test_api_security.py). **9 funções / 17 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_api_security--test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length"></a>[`test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length`](../tests/test_api_security.py#L66) | ASGI local | Corpo de 40.000 bytes retorna 413 com tamanho ausente, falso pequeno ou declarado excessivo; declaração grande é recusada antes de ler. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_exact_size_limit_preserves_body_for_validation"></a>[`test_exact_size_limit_preserves_body_for_validation`](../tests/test_api_security.py#L79) | ASGI local | JSON de exatos 32KiB é aceito pelo middleware e chega íntegro ao endpoint; Content-Type com charset é aceito. É teste ASGI local, não valida o schema Pix. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_pix_requires_json_content_type"></a>[`test_pix_requires_json_content_type`](../tests/test_api_security.py#L92) | ASGI local | Tipo ausente, text/plain e application/xml retornam 415 antes da leitura. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_malformed_content_length_is_rejected"></a>[`test_malformed_content_length_is_rejected`](../tests/test_api_security.py#L100) | ASGI local | Content-Length negativo,NaN,decimal ou com sinal+ retorna 400. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_body_read_has_total_deadline"></a>[`test_body_read_has_total_deadline`](../tests/test_api_security.py#L111) | ASGI local | Simula deadline curto e leitura lenta; retorna 408 ao expirar o prazo total. O padrão do middleware é 10s. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_request_without_internal_token_reaches_endpoint_and_sets_security_headers"></a>[`test_request_without_internal_token_reaches_endpoint_and_sets_security_headers`](../tests/test_api_security.py#L121) | ASGI local | Endpoint ASGI local aceita token ausente/incorreto e retorna no-store,nosniff e identificador de requisição. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_unhandled_error_does_not_leak_exception_details_and_is_correlated"></a>[`test_unhandled_error_does_not_leak_exception_details_and_is_correlated`](../tests/test_api_security.py#L137) | ASGI local | Exceção simulada retorna 500/PIX000500; texto sensível não aparece em resposta/logs; ID correlaciona log e resposta. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_success_and_not_found_http_responses_prohibit_caching"></a>[`test_success_and_not_found_http_responses_prohibit_caching`](../tests/test_api_security.py#L154) | HTTP | POST,GET existente eGET ausente recebem no-store e nosniff. | [P13 — Proteções HTTP](politicas-negocio.md#p13) |
| <a id="test_api_security--test_oversized_http_request_does_not_consume_transaction_id"></a>[`test_oversized_http_request_does_not_consume_transaction_id`](../tests/test_api_security.py#L165) | HTTP | Pedido grande retorna 413 com no-store e não cria análise: GET do ID retorna 404. | [P13 — Proteções HTTP](politicas-negocio.md#p13)<br>[P10 — Contrato e validação](politicas-negocio.md#p10) |

**Casos individuais de `test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_api_security--test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `declared=None` | [P13](politicas-negocio.md#p13) |
| 2 | — | `declared=b'1'` | [P13](politicas-negocio.md#p13) |
| 3 | — | `declared=str(MAX_REQUEST_BYTES + 1).encode()` | [P13](politicas-negocio.md#p13) |

**Casos individuais de `test_pix_requires_json_content_type` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_api_security--test_pix_requires_json_content_type). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `content_type=None` | [P13](politicas-negocio.md#p13) |
| 2 | — | `content_type=b'text/plain'` | [P13](politicas-negocio.md#p13) |
| 3 | — | `content_type=b'application/xml'` | [P13](politicas-negocio.md#p13) |

**Casos individuais de `test_malformed_content_length_is_rejected` (4)**

Todos verificam o cenário e as políticas da [análise da função](#test_api_security--test_malformed_content_length_is_rejected). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `declared=b'-1'` | [P13](politicas-negocio.md#p13) |
| 2 | — | `declared=b'NaN'` | [P13](politicas-negocio.md#p13) |
| 3 | — | `declared=b'1.5'` | [P13](politicas-negocio.md#p13) |
| 4 | — | `declared=b'+2'` | [P13](politicas-negocio.md#p13) |

**Casos individuais de `test_request_without_internal_token_reaches_endpoint_and_sets_security_headers` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_api_security--test_request_without_internal_token_reaches_endpoint_and_sets_security_headers). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `token=None` | [P13](politicas-negocio.md#p13) |
| 2 | — | `token=b'wrong-token'` | [P13](politicas-negocio.md#p13) |

<a id="suite-27"></a>

### 27. Resposta pública, explicabilidade e auditoria interna

Fonte: [test_metadata.py](../tests/test_metadata.py). **11 funções / 21 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_metadata--test_minimal_http_response_details_and_saved_audit"></a>[`test_minimal_http_response_details_and_saved_audit`](../tests/test_metadata.py#L21) | HTTP + PostgreSQL | POST/GET/reenvio trazem resumo mínimo; include_details só acrescenta nomes. Banco preserva política, tempo e avaliação temporal completos. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_metadata--test_hard_limit_has_readable_rule_name"></a>[`test_hard_limit_has_readable_rule_name`](../tests/test_metadata.py#L45) | HTTP | Rejeição por R$ 30mil mostra nome legível do limite; metadados públicos continuam restritos ao contrato. | [R02 — Montante](politicas-negocio.md#r02)<br>[P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_metadata--test_approved_http_response_has_empty_rules_only_when_requested"></a>[`test_approved_http_response_has_empty_rules_only_when_requested`](../tests/test_metadata.py#L58) | HTTP + PostgreSQL | Aprovação score zero omite rules no resumo; detalhes deGET/POST exibem lista vazia. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_metadata--test_processing_timer_covers_analysis_and_is_not_recomputed"></a>[`test_processing_timer_covers_analysis_and_is_not_recomputed`](../tests/test_metadata.py#L73) | Unitário | Relógio simulado mede 12,345ms antes de criar a linha; commit ocorre uma vez e reenvio não recalcula duração nem recria análise. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_metadata--test_legacy_summary_does_not_change_evidence"></a>[`test_legacy_summary_does_not_change_evidence`](../tests/test_metadata.py#L102) | Unitário | Evidência v2 legada recebe alias de valor e não inventa score do grafo; projeção não muta snapshot. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_metadata--test_factor_list_and_uncapped_sum_stay_internal"></a>[`test_factor_list_and_uncapped_sum_stay_internal`](../tests/test_metadata.py#L120) | Unitário | Formatos legados de mapa/lista normalizam fatores e soma 160 com score 100; soma e fatores permanecem internos e entrada não é alterada. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P02 — Score e tetos](politicas-negocio.md#p02) |
| <a id="test_metadata--test_all_current_rules_have_readable_aliases"></a>[`test_all_current_rules_have_readable_aliases`](../tests/test_metadata.py#L141) | Unitário | Todos os códigos configurados possuem alias legível e aliases não contêm sublinhado técnico. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_metadata--test_public_graph_score_is_present_only_when_available"></a>[`test_public_graph_score_is_present_only_when_available`](../tests/test_metadata.py#L160) | Unitário | Score ausente/off/indisponível/sem histórico/falha é omitido;0 e 97,3076 aparecem; legado é compatível e snapshot v2 tem preferência sobre v1. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P09 — Grafo temporal v2](politicas-negocio.md#p09) |
| <a id="test_metadata--test_details_only_list_effective_rules_and_mandatory_controls"></a>[`test_details_only_list_effective_rules_and_mandatory_controls`](../tests/test_metadata.py#L175) | Unitário | Omite regra atenuada de contribuiçãozero, deduplica nomes e preserva limite forte/primeiro Pix usados como controles mesmo com contribuiçãozero. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P01 — Prioridade de decisão](politicas-negocio.md#p01) |
| <a id="test_metadata--test_rule_names_explain_accumulated_risk_overrides"></a>[`test_rule_names_explain_accumulated_risk_overrides`](../tests/test_metadata.py#L206) | Unitário | Intervenções por conta ou titular aparecem nos detalhes com os respectivos nomes legíveis, mesmo sem regra transacional. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[P07 — Titular e vínculos](politicas-negocio.md#p07) |
| <a id="test_metadata--test_no_rules_returns_empty_details_instead_of_a_no_rule_alias"></a>[`test_no_rules_returns_empty_details_instead_of_a_no_rule_alias`](../tests/test_metadata.py#L215) | Unitário | Ausência de regras retorna lista vazia; marcador interno no_rule_triggered não vira nome público. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |

**Casos individuais de `test_factor_list_and_uncapped_sum_stay_internal` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_metadata--test_factor_list_and_uncapped_sum_stay_internal). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `legacy_mapping=True` | [P12](politicas-negocio.md#p12)<br>[P02](politicas-negocio.md#p02) |
| 2 | — | `legacy_mapping=False` | [P12](politicas-negocio.md#p12)<br>[P02](politicas-negocio.md#p02) |

**Casos individuais de `test_public_graph_score_is_present_only_when_available` (9)**

Todos verificam o cenário e as políticas da [análise da função](#test_metadata--test_public_graph_score_is_present_only_when_available). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `graph={}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 2 | — | `graph={'gnn_v2': {'mode': 'off', 'gnn_score': None}}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 3 | — | `graph={'gnn_v2': {'mode': 'shadow', 'status': 'unavailable', 'gnn_score': None}}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 4 | — | `graph={'gnn_v2': {'mode': 'shadow', 'status': 'insufficient_history'}}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 5 | — | `graph={'gnn_v2': {'mode': 'shadow', 'status': 'inference_failed', 'gnn_score': None}}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 6 | — | `graph={'gnn_v2': {'mode': 'shadow', 'gnn_score': 0}}; expected_score=0` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 7 | — | `graph={'gnn_v2': {'mode': 'shadow', 'gnn_score': 97.3076, 'applied_points': 0}}; expected_score=97.3076` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 8 | — | `graph={'gnn': {'mode': 'contribute', 'gnn_score': 82, 'applied_points': 20}}; expected_score=82` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |
| 9 | — | `graph={'gnn_v2': {'mode': 'off'}, 'gnn': {'mode': 'shadow', 'gnn_score': 80}}; expected_score=None` | [P12](politicas-negocio.md#p12)<br>[P09](politicas-negocio.md#p09) |

**Casos individuais de `test_rule_names_explain_accumulated_risk_overrides` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_metadata--test_rule_names_explain_accumulated_risk_overrides). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `cause='account_untrust'; label='Desconfiança acumulada da conta'` | [P12](politicas-negocio.md#p12)<br>[P06](politicas-negocio.md#p06)<br>[P07](politicas-negocio.md#p07) |
| 2 | — | `cause='own_entity_untrust'; label='Desconfiança acumulada do titular'` | [P12](politicas-negocio.md#p12)<br>[P06](politicas-negocio.md#p06)<br>[P07](politicas-negocio.md#p07) |

<a id="suite-28"></a>

### 28. Elegibilidade do histórico e imutabilidade

Fonte: [test_history_audit.py](../tests/test_history_audit.py). **6 funções / 13 casos.**

| Teste implementado | Nível | Em que consiste e resultado esperado | Política de negócio abordada |
|---|---|---|---|
| <a id="test_history_audit--test_history_status_eligibility_is_explicit"></a>[`test_history_status_eligibility_is_explicit`](../tests/test_history_audit.py#L47) | PostgreSQL + controlador/repositório | Para aprovado/pendente/rejeitado, todos contam como tentativa/montante; somente aprovado gera referência, familiaridade e contagem de aprovação. | [P03 — Históricos elegíveis](politicas-negocio.md#p03) |
| <a id="test_history_audit--test_familiarity_expires_but_amount_profile_has_no_day_cutoff"></a>[`test_familiarity_expires_but_amount_profile_has_no_day_cutoff`](../tests/test_history_audit.py#L77) | PostgreSQL + controlador/repositório | Aprovação exatamente 30dias atrás estabelece familiaridade;30dias+1s não, mas ainda forma perfil. Evento futuro não alimenta nenhum. | [P03 — Históricos elegíveis](politicas-negocio.md#p03)<br>[R08 — Desvio de perfil](politicas-negocio.md#r08) |
| <a id="test_history_audit--test_database_refuses_history_mutation"></a>[`test_database_refuses_history_mutation`](../tests/test_history_audit.py#L96) | PostgreSQL + controlador/repositório | UPDATE eDELETE na tabela geram IntegrityError por trigger; valor original permanece. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12) |
| <a id="test_history_audit--test_committed_payload_and_evidence_survive_new_connection"></a>[`test_committed_payload_and_evidence_survive_new_connection`](../tests/test_history_audit.py#L112) | HTTP + PostgreSQL | Para cada um dos três status, nova conexão física encontra payload normalizado, hash, identidades, decisão e metadados idênticos; GET/reenvio concordam. | [P12 — Auditoria e explicabilidade](politicas-negocio.md#p12)<br>[P11 — Idempotência e concorrência](politicas-negocio.md#p11) |
| <a id="test_history_audit--test_receiving_pix_does_not_establish_outgoing_payer_profile"></a>[`test_receiving_pix_does_not_establish_outgoing_payer_profile`](../tests/test_history_audit.py#L137) | HTTP + PostgreSQL | Pix recebido pelo titular não vira histórico de envio; seu primeiro envio≥R$ 500 continua exigindo 2FA por primeira transação. | [P03 — Históricos elegíveis](politicas-negocio.md#p03)<br>[R03 — Primeiro Pix](politicas-negocio.md#r03) |
| <a id="test_history_audit--test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls"></a>[`test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls`](../tests/test_history_audit.py#L151) | PostgreSQL + controlador/repositório | Aprovação legada sem identidade da origem mantém perfil/familiaridade por pagador, mas não entra na duplicidade nem no acumulado por conta. | [P03 — Históricos elegíveis](politicas-negocio.md#p03)<br>[P06 — Suspeita própria da conta](politicas-negocio.md#p06)<br>[R13 — Possível duplicidade](politicas-negocio.md#r13) |

**Casos individuais de `test_history_status_eligibility_is_explicit` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_history_audit--test_history_status_eligibility_is_explicit). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `status='approved'` | [P03](politicas-negocio.md#p03) |
| 2 | — | `status='two_factor_required'` | [P03](politicas-negocio.md#p03) |
| 3 | — | `status='rejected'` | [P03](politicas-negocio.md#p03) |

**Casos individuais de `test_familiarity_expires_but_amount_profile_has_no_day_cutoff` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_history_audit--test_familiarity_expires_but_amount_profile_has_no_day_cutoff). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `seconds=30 * 86400; known=True` | [P03](politicas-negocio.md#p03)<br>[R08](politicas-negocio.md#r08) |
| 2 | — | `seconds=30 * 86400 + 1; known=False` | [P03](politicas-negocio.md#p03)<br>[R08](politicas-negocio.md#r08) |
| 3 | — | `seconds=-1; known=False` | [P03](politicas-negocio.md#p03)<br>[R08](politicas-negocio.md#r08) |

**Casos individuais de `test_database_refuses_history_mutation` (2)**

Todos verificam o cenário e as políticas da [análise da função](#test_history_audit--test_database_refuses_history_mutation). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | update | `operation=update` | [P12](politicas-negocio.md#p12) |
| 2 | delete | `operation=delete` | [P12](politicas-negocio.md#p12) |

**Casos individuais de `test_committed_payload_and_evidence_survive_new_connection` (3)**

Todos verificam o cenário e as políticas da [análise da função](#test_history_audit--test_committed_payload_and_evidence_survive_new_connection). Índices abaixo são identificadores editoriais; não substituem os node IDs do pytest.

| Caso | Identificação explícita no código | Argumentos da variação e expectativas declaradas | Política |
|---|---|---|---|
| 1 | — | `expected='approved'` | [P12](politicas-negocio.md#p12)<br>[P11](politicas-negocio.md#p11) |
| 2 | — | `expected='two_factor_required'` | [P12](politicas-negocio.md#p12)<br>[P11](politicas-negocio.md#p11) |
| 3 | — | `expected='rejected'` | [P12](politicas-negocio.md#p12)<br>[P11](politicas-negocio.md#p11) |

## Matriz inversa: política → testes que a verificam

Esta matriz permite começar pela regra de negócio e encontrar todas as análises individuais relacionadas. Uma função pode verificar mais de uma política; isso não significa fatores de risco independentes.

<a id="cobertura-r01"></a>

### R01 — Frequência

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_low_value_without_history_still_respects_other_controls`](#test_no_history--test_low_value_without_history_still_respects_other_controls)
- [`test_duplicate_payment.py::test_duplicate_never_overrides_a_hard_rejection`](#test_duplicate_payment--test_duplicate_never_overrides_a_hard_rejection)
- [`test_access_patterns.py::test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits`](#test_access_patterns--test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits)
- [`test_risk_score.py::test_activity_group_cap_preserves_all_hard_reasons`](#test_risk_score--test_activity_group_cap_preserves_all_hard_reasons)
- [`test_contextual_trust.py::test_familiar_relationship_never_neutralizes_independent_controls`](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls)
- [`test_account_untrust.py::test_active_block_does_not_refresh_itself_even_on_velocity_risk`](#test_account_untrust--test_active_block_does_not_refresh_itself_even_on_velocity_risk)
- [`test_pix.py::test_sixth_attempt_is_rejected_and_rejections_are_saved`](#test_pix--test_sixth_attempt_is_rejected_and_rejections_are_saved)
- [`test_pix.py::test_retries_do_not_inflate_velocity`](#test_pix--test_retries_do_not_inflate_velocity)
- [`test_pix.py::test_velocity_window_and_future_history`](#test_pix--test_velocity_window_and_future_history)
- [`test_pix.py::test_concurrent_distinct_pix_cannot_bypass_velocity`](#test_pix--test_concurrent_distinct_pix_cannot_bypass_velocity)
- [`test_pix.py::test_velocity_is_shared_by_payer_across_accounts`](#test_pix--test_velocity_is_shared_by_payer_across_accounts)

<a id="cobertura-r02"></a>

### R02 — Montante

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_low_value_without_history_still_respects_other_controls`](#test_no_history--test_low_value_without_history_still_respects_other_controls)
- [`test_duplicate_payment.py::test_rejected_attempt_is_not_a_possible_previous_payment`](#test_duplicate_payment--test_rejected_attempt_is_not_a_possible_previous_payment)
- [`test_scoring_policy.py::test_missing_reference_priority_survives_zero_weights`](#test_scoring_policy--test_missing_reference_priority_survives_zero_weights)
- [`test_risk_score.py::test_activity_group_cap_preserves_all_hard_reasons`](#test_risk_score--test_activity_group_cap_preserves_all_hard_reasons)
- [`test_contextual_trust.py::test_familiar_relationship_never_neutralizes_independent_controls`](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls)
- [`test_temporal_live.py::test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions)
- [`test_pix.py::test_all_reasons_and_rejection_priority`](#test_pix--test_all_reasons_and_rejection_priority)
- [`test_pix.py::test_accumulated_value_boundary`](#test_pix--test_accumulated_value_boundary)
- [`test_metadata.py::test_hard_limit_has_readable_rule_name`](#test_metadata--test_hard_limit_has_readable_rule_name)

<a id="cobertura-r03"></a>

### R03 — Primeiro Pix

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_no_history_amount_floor`](#test_no_history--test_no_history_amount_floor)
- [`test_no_history.py::test_no_history_amount_floor_is_configurable`](#test_no_history--test_no_history_amount_floor_is_configurable)
- [`test_no_history.py::test_low_value_without_history_still_respects_other_controls`](#test_no_history--test_low_value_without_history_still_respects_other_controls)
- [`test_no_history.py::test_first_pix_http_boundary_and_replay`](#test_no_history--test_first_pix_http_boundary_and_replay)
- [`test_scoring_policy.py::test_missing_reference_priority_survives_zero_weights`](#test_scoring_policy--test_missing_reference_priority_survives_zero_weights)
- [`test_risk_score.py::test_first_pix_requests_two_factor_and_saves_explanation`](#test_risk_score--test_first_pix_requests_two_factor_and_saves_explanation)
- [`test_account_untrust.py::test_first_transaction_and_account_age_alone_do_not_build_untrust`](#test_account_untrust--test_first_transaction_and_account_age_alone_do_not_build_untrust)
- [`test_temporal_live.py::test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions)
- [`test_pix.py::test_all_reasons_and_rejection_priority`](#test_pix--test_all_reasons_and_rejection_priority)
- [`test_history_audit.py::test_receiving_pix_does_not_establish_outgoing_payer_profile`](#test_history_audit--test_receiving_pix_does_not_establish_outgoing_payer_profile)

<a id="cobertura-r04"></a>

### R04 — Referência insuficiente

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_no_history_amount_floor`](#test_no_history--test_no_history_amount_floor)
- [`test_no_history.py::test_no_history_amount_floor_is_configurable`](#test_no_history--test_no_history_amount_floor_is_configurable)
- [`test_no_history.py::test_low_value_without_history_still_respects_other_controls`](#test_no_history--test_low_value_without_history_still_respects_other_controls)
- [`test_no_history.py::test_pending_attempt_cannot_raise_the_reference_for_a_small_pix`](#test_no_history--test_pending_attempt_cannot_raise_the_reference_for_a_small_pix)
- [`test_dynamic_profile.py::test_pending_two_factor_pix_cannot_bootstrap_amount_history`](#test_dynamic_profile--test_pending_two_factor_pix_cannot_bootstrap_amount_history)
- [`test_dynamic_profile.py::test_old_pending_attempts_never_establish_value_or_familiarity`](#test_dynamic_profile--test_old_pending_attempts_never_establish_value_or_familiarity)
- [`test_scoring_policy.py::test_missing_reference_priority_survives_zero_weights`](#test_scoring_policy--test_missing_reference_priority_survives_zero_weights)
- [`test_temporal_live.py::test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions)

<a id="cobertura-r05"></a>

### R05 — Origem recente

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_risk_score.py::test_high_profile_plus_new_account_rejects`](#test_risk_score--test_high_profile_plus_new_account_rejects)
- [`test_contextual_trust.py::test_destination_evidence_intervenes_without_accusing_the_sender`](#test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender)
- [`test_account_untrust.py::test_first_transaction_and_account_age_alone_do_not_build_untrust`](#test_account_untrust--test_first_transaction_and_account_age_alone_do_not_build_untrust)
- [`test_pix.py::test_all_reasons_and_rejection_priority`](#test_pix--test_all_reasons_and_rejection_priority)

<a id="cobertura-r06"></a>

### R06 — Destino recente

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)
- [`test_risk_score.py::test_approved_history_makes_device_and_young_destination_familiar`](#test_risk_score--test_approved_history_makes_device_and_young_destination_familiar)
- [`test_risk_score.py::test_related_counterparty_signals_are_capped`](#test_risk_score--test_related_counterparty_signals_are_capped)
- [`test_contextual_trust.py::test_destination_evidence_intervenes_without_accusing_the_sender`](#test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender)
- [`test_pix.py::test_new_destination_scores_only_above_minimum`](#test_pix--test_new_destination_scores_only_above_minimum)

<a id="cobertura-r07"></a>

### R07 — Destino desconhecido

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)
- [`test_risk_score.py::test_approved_history_makes_device_and_young_destination_familiar`](#test_risk_score--test_approved_history_makes_device_and_young_destination_familiar)
- [`test_risk_score.py::test_two_weak_groups_combine_into_two_factor`](#test_risk_score--test_two_weak_groups_combine_into_two_factor)
- [`test_risk_score.py::test_related_counterparty_signals_are_capped`](#test_risk_score--test_related_counterparty_signals_are_capped)
- [`test_contextual_trust.py::test_destination_evidence_intervenes_without_accusing_the_sender`](#test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender)
- [`test_contextual_trust.py::test_mixed_sender_and_destination_evidence_preserves_only_own_increment`](#test_contextual_trust--test_mixed_sender_and_destination_evidence_preserves_only_own_increment)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)

<a id="cobertura-r08"></a>

### R08 — Desvio de perfil

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_pending_attempt_cannot_raise_the_reference_for_a_small_pix`](#test_no_history--test_pending_attempt_cannot_raise_the_reference_for_a_small_pix)
- [`test_dynamic_profile.py::test_reference_average_is_independent_of_available_sample_count`](#test_dynamic_profile--test_reference_average_is_independent_of_available_sample_count)
- [`test_dynamic_profile.py::test_fractional_average_is_compared_exactly_and_policy_is_configurable`](#test_dynamic_profile--test_fractional_average_is_compared_exactly_and_policy_is_configurable)
- [`test_dynamic_profile.py::test_repository_uses_last_ten_approved_pix_without_day_cutoff`](#test_dynamic_profile--test_repository_uses_last_ten_approved_pix_without_day_cutoff)
- [`test_dynamic_profile.py::test_rejected_and_pending_attempts_do_not_inflate_approved_profile`](#test_dynamic_profile--test_rejected_and_pending_attempts_do_not_inflate_approved_profile)
- [`test_risk_score.py::test_high_profile_signal_alone_requires_two_factor`](#test_risk_score--test_high_profile_signal_alone_requires_two_factor)
- [`test_risk_score.py::test_high_profile_plus_new_account_rejects`](#test_risk_score--test_high_profile_plus_new_account_rejects)
- [`test_contextual_trust.py::test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence`](#test_contextual_trust--test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)
- [`test_untrust_contrasts.py::test_reclassifying_real_profile_evidence_does_not_erase_suspicion`](#test_untrust_contrasts--test_reclassifying_real_profile_evidence_does_not_erase_suspicion)
- [`test_untrust_replay.py::test_replay_agrees_with_persisted_decisions_at_each_step`](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step)
- [`test_history_audit.py::test_familiarity_expires_but_amount_profile_has_no_day_cutoff`](#test_history_audit--test_familiarity_expires_but_amount_profile_has_no_day_cutoff)

<a id="cobertura-r09"></a>

### R09 — Aparelho desconhecido

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_access_patterns.py::test_repository_novel_app_night_combines_context_with_device`](#test_access_patterns--test_repository_novel_app_night_combines_context_with_device)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)
- [`test_risk_score.py::test_approved_history_makes_device_and_young_destination_familiar`](#test_risk_score--test_approved_history_makes_device_and_young_destination_familiar)
- [`test_risk_score.py::test_weak_device_signal_alone_approves`](#test_risk_score--test_weak_device_signal_alone_approves)
- [`test_risk_score.py::test_two_weak_groups_combine_into_two_factor`](#test_risk_score--test_two_weak_groups_combine_into_two_factor)
- [`test_contextual_trust.py::test_familiar_relationship_never_neutralizes_independent_controls`](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls)
- [`test_contextual_trust.py::test_mixed_sender_and_destination_evidence_preserves_only_own_increment`](#test_contextual_trust--test_mixed_sender_and_destination_evidence_preserves_only_own_increment)
- [`test_account_untrust.py::test_single_low_risk_novelty_does_not_accumulate`](#test_account_untrust--test_single_low_risk_novelty_does_not_accumulate)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)

<a id="cobertura-r10"></a>

### R10 — Aparelho compartilhado

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_no_history.py::test_low_value_without_history_still_respects_other_controls`](#test_no_history--test_low_value_without_history_still_respects_other_controls)
- [`test_access_patterns.py::test_shared_device_counts_distinct_owners_and_excludes_old_future_events`](#test_access_patterns--test_shared_device_counts_distinct_owners_and_excludes_old_future_events)
- [`test_access_patterns.py::test_shared_device_concurrency_sees_prior_commits`](#test_access_patterns--test_shared_device_concurrency_sees_prior_commits)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)
- [`test_contextual_trust.py::test_familiar_relationship_never_neutralizes_independent_controls`](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)
- [`test_temporal_gnn.py::test_holder_identity_deduplicates_accounts_on_a_shared_device`](#test_temporal_gnn--test_holder_identity_deduplicates_accounts_on_a_shared_device)

<a id="cobertura-r11"></a>

### R11 — Múltiplos aparelhos

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_access_patterns.py::test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate`](#test_access_patterns--test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)

<a id="cobertura-r12"></a>

### R12 — Uso noturno do app

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_access_patterns.py::test_night_rule_uses_app_and_brasilia_boundaries`](#test_access_patterns--test_night_rule_uses_app_and_brasilia_boundaries)
- [`test_access_patterns.py::test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits`](#test_access_patterns--test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits)
- [`test_access_patterns.py::test_configured_night_start_controls_the_signal`](#test_access_patterns--test_configured_night_start_controls_the_signal)
- [`test_access_patterns.py::test_repository_recognizes_habitual_night_use`](#test_access_patterns--test_repository_recognizes_habitual_night_use)
- [`test_access_patterns.py::test_repository_novel_app_night_combines_context_with_device`](#test_access_patterns--test_repository_novel_app_night_combines_context_with_device)

<a id="cobertura-r13"></a>

### R13 — Possível duplicidade

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_duplicate_payment.py::test_duplicate_window_and_future_exclusion`](#test_duplicate_payment--test_duplicate_window_and_future_exclusion)
- [`test_duplicate_payment.py::test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed`](#test_duplicate_payment--test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed)
- [`test_duplicate_payment.py::test_different_payment_identity_does_not_trigger_duplicate`](#test_duplicate_payment--test_different_payment_identity_does_not_trigger_duplicate)
- [`test_duplicate_payment.py::test_changed_device_and_opening_dates_do_not_hide_duplicate`](#test_duplicate_payment--test_changed_device_and_opening_dates_do_not_hide_duplicate)
- [`test_duplicate_payment.py::test_rejected_attempt_is_not_a_possible_previous_payment`](#test_duplicate_payment--test_rejected_attempt_is_not_a_possible_previous_payment)
- [`test_duplicate_payment.py::test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent`](#test_duplicate_payment--test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent)
- [`test_duplicate_payment.py::test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust`](#test_duplicate_payment--test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust)
- [`test_duplicate_payment.py::test_repository_respects_custom_duplicate_window`](#test_duplicate_payment--test_repository_respects_custom_duplicate_window)
- [`test_duplicate_payment.py::test_duplicate_never_overrides_a_hard_rejection`](#test_duplicate_payment--test_duplicate_never_overrides_a_hard_rejection)
- [`test_untrust_replay.py::test_replay_agrees_with_persisted_decisions_at_each_step`](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step)
- [`test_history_audit.py::test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls`](#test_history_audit--test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls)

<a id="cobertura-p01"></a>

### P01 — Prioridade de decisão

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_dynamic_profile.py::test_reference_average_is_independent_of_available_sample_count`](#test_dynamic_profile--test_reference_average_is_independent_of_available_sample_count)
- [`test_duplicate_payment.py::test_duplicate_never_overrides_a_hard_rejection`](#test_duplicate_payment--test_duplicate_never_overrides_a_hard_rejection)
- [`test_scoring_policy.py::test_score_boundaries_and_rejection_factor_guard`](#test_scoring_policy--test_score_boundaries_and_rejection_factor_guard)
- [`test_scoring_policy.py::test_decision_uses_configured_thresholds`](#test_scoring_policy--test_decision_uses_configured_thresholds)
- [`test_scoring_policy.py::test_configured_rejection_requires_three_positive_factors`](#test_scoring_policy--test_configured_rejection_requires_three_positive_factors)
- [`test_scoring_policy.py::test_missing_reference_priority_survives_zero_weights`](#test_scoring_policy--test_missing_reference_priority_survives_zero_weights)
- [`test_risk_factors.py::test_increasing_factor_weights_can_block_a_transaction`](#test_risk_factors--test_increasing_factor_weights_can_block_a_transaction)
- [`test_risk_factors.py::test_rule_remapping_changes_factor_cap_and_rejection_guard`](#test_risk_factors--test_rule_remapping_changes_factor_cap_and_rejection_guard)
- [`test_risk_score.py::test_weak_device_signal_alone_approves`](#test_risk_score--test_weak_device_signal_alone_approves)
- [`test_risk_score.py::test_two_weak_groups_combine_into_two_factor`](#test_risk_score--test_two_weak_groups_combine_into_two_factor)
- [`test_risk_score.py::test_high_profile_signal_alone_requires_two_factor`](#test_risk_score--test_high_profile_signal_alone_requires_two_factor)
- [`test_risk_score.py::test_high_profile_plus_new_account_rejects`](#test_risk_score--test_high_profile_plus_new_account_rejects)
- [`test_account_untrust.py::test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control`](#test_account_untrust--test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)
- [`test_entity_risk.py::test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved`](#test_entity_risk--test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved)
- [`test_temporal_live.py::test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions)
- [`test_graph_untrust_experiment.py::test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate`](#test_graph_untrust_experiment--test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate)
- [`test_pix.py::test_all_reasons_and_rejection_priority`](#test_pix--test_all_reasons_and_rejection_priority)
- [`test_metadata.py::test_details_only_list_effective_rules_and_mandatory_controls`](#test_metadata--test_details_only_list_effective_rules_and_mandatory_controls)

<a id="cobertura-p02"></a>

### P02 — Score e tetos

- [`test_rule_audit.py::test_each_rule_activation_boundary_and_exclusions`](#test_rule_audit--test_each_rule_activation_boundary_and_exclusions)
- [`test_access_patterns.py::test_repository_novel_app_night_combines_context_with_device`](#test_access_patterns--test_repository_novel_app_night_combines_context_with_device)
- [`test_risk_factors.py::test_fractional_factor_weight_is_truncated_before_decision_and_explained`](#test_risk_factors--test_fractional_factor_weight_is_truncated_before_decision_and_explained)
- [`test_risk_factors.py::test_increasing_factor_weights_can_block_a_transaction`](#test_risk_factors--test_increasing_factor_weights_can_block_a_transaction)
- [`test_risk_factors.py::test_rule_remapping_changes_factor_cap_and_rejection_guard`](#test_risk_factors--test_rule_remapping_changes_factor_cap_and_rejection_guard)
- [`test_risk_factors.py::test_related_rules_share_one_factor_and_reconstruct_capped_score`](#test_risk_factors--test_related_rules_share_one_factor_and_reconstruct_capped_score)
- [`test_risk_factors.py::test_every_rule_references_a_valid_factor`](#test_risk_factors--test_every_rule_references_a_valid_factor)
- [`test_risk_score.py::test_related_counterparty_signals_are_capped`](#test_risk_score--test_related_counterparty_signals_are_capped)
- [`test_risk_score.py::test_factor_sum_can_exceed_final_score_cap`](#test_risk_score--test_factor_sum_can_exceed_final_score_cap)
- [`test_risk_score.py::test_activity_group_cap_preserves_all_hard_reasons`](#test_risk_score--test_activity_group_cap_preserves_all_hard_reasons)
- [`test_untrust_contrasts.py::test_correlated_device_signals_accumulate_only_the_capped_contribution`](#test_untrust_contrasts--test_correlated_device_signals_accumulate_only_the_capped_contribution)
- [`test_entity_risk.py::test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence`](#test_entity_risk--test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence)
- [`test_metadata.py::test_factor_list_and_uncapped_sum_stay_internal`](#test_metadata--test_factor_list_and_uncapped_sum_stay_internal)

<a id="cobertura-p03"></a>

### P03 — Históricos elegíveis

- [`test_no_history.py::test_pending_attempt_cannot_raise_the_reference_for_a_small_pix`](#test_no_history--test_pending_attempt_cannot_raise_the_reference_for_a_small_pix)
- [`test_dynamic_profile.py::test_repository_uses_last_ten_approved_pix_without_day_cutoff`](#test_dynamic_profile--test_repository_uses_last_ten_approved_pix_without_day_cutoff)
- [`test_dynamic_profile.py::test_pending_two_factor_pix_cannot_bootstrap_amount_history`](#test_dynamic_profile--test_pending_two_factor_pix_cannot_bootstrap_amount_history)
- [`test_dynamic_profile.py::test_rejected_and_pending_attempts_do_not_inflate_approved_profile`](#test_dynamic_profile--test_rejected_and_pending_attempts_do_not_inflate_approved_profile)
- [`test_dynamic_profile.py::test_old_pending_attempts_never_establish_value_or_familiarity`](#test_dynamic_profile--test_old_pending_attempts_never_establish_value_or_familiarity)
- [`test_access_patterns.py::test_shared_device_counts_distinct_owners_and_excludes_old_future_events`](#test_access_patterns--test_shared_device_counts_distinct_owners_and_excludes_old_future_events)
- [`test_access_patterns.py::test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate`](#test_access_patterns--test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate)
- [`test_access_patterns.py::test_repository_recognizes_habitual_night_use`](#test_access_patterns--test_repository_recognizes_habitual_night_use)
- [`test_risk_score.py::test_approved_history_makes_device_and_young_destination_familiar`](#test_risk_score--test_approved_history_makes_device_and_young_destination_familiar)
- [`test_contextual_trust.py::test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust`](#test_contextual_trust--test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust)
- [`test_contextual_trust_db.py::test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals`](#test_contextual_trust_db--test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals)
- [`test_contextual_trust_db.py::test_destination_attempts_remain_in_history_without_tainting_normal_next_payment`](#test_contextual_trust_db--test_destination_attempts_remain_in_history_without_tainting_normal_next_payment)
- [`test_untrust_replay.py::test_replay_agrees_with_persisted_decisions_at_each_step`](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step)
- [`test_pix.py::test_sixth_attempt_is_rejected_and_rejections_are_saved`](#test_pix--test_sixth_attempt_is_rejected_and_rejections_are_saved)
- [`test_pix.py::test_velocity_window_and_future_history`](#test_pix--test_velocity_window_and_future_history)
- [`test_pix.py::test_velocity_is_shared_by_payer_across_accounts`](#test_pix--test_velocity_is_shared_by_payer_across_accounts)
- [`test_history_audit.py::test_history_status_eligibility_is_explicit`](#test_history_audit--test_history_status_eligibility_is_explicit)
- [`test_history_audit.py::test_familiarity_expires_but_amount_profile_has_no_day_cutoff`](#test_history_audit--test_familiarity_expires_but_amount_profile_has_no_day_cutoff)
- [`test_history_audit.py::test_receiving_pix_does_not_establish_outgoing_payer_profile`](#test_history_audit--test_receiving_pix_does_not_establish_outgoing_payer_profile)
- [`test_history_audit.py::test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls`](#test_history_audit--test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls)

<a id="cobertura-p04"></a>

### P04 — Configuração do operador

- [`test_rule_audit.py::test_every_configured_rule_has_positive_and_negative_audit_cases`](#test_rule_audit--test_every_configured_rule_has_positive_and_negative_audit_cases)
- [`test_no_history.py::test_no_history_amount_floor_is_configurable`](#test_no_history--test_no_history_amount_floor_is_configurable)
- [`test_no_history.py::test_no_history_amount_floor_requires_positive_integer_cents`](#test_no_history--test_no_history_amount_floor_requires_positive_integer_cents)
- [`test_dynamic_profile.py::test_fractional_average_is_compared_exactly_and_policy_is_configurable`](#test_dynamic_profile--test_fractional_average_is_compared_exactly_and_policy_is_configurable)
- [`test_dynamic_profile.py::test_invalid_dynamic_profile_configuration`](#test_dynamic_profile--test_invalid_dynamic_profile_configuration)
- [`test_duplicate_payment.py::test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust`](#test_duplicate_payment--test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust)
- [`test_duplicate_payment.py::test_repository_respects_custom_duplicate_window`](#test_duplicate_payment--test_repository_respects_custom_duplicate_window)
- [`test_duplicate_payment.py::test_invalid_duplicate_window`](#test_duplicate_payment--test_invalid_duplicate_window)
- [`test_access_patterns.py::test_configured_night_start_controls_the_signal`](#test_access_patterns--test_configured_night_start_controls_the_signal)
- [`test_access_patterns.py::test_invalid_access_policy`](#test_access_patterns--test_invalid_access_policy)
- [`test_scoring_policy.py::test_decision_uses_configured_thresholds`](#test_scoring_policy--test_decision_uses_configured_thresholds)
- [`test_scoring_policy.py::test_configured_rejection_requires_three_positive_factors`](#test_scoring_policy--test_configured_rejection_requires_three_positive_factors)
- [`test_scoring_policy.py::test_invalid_policy_cannot_be_activated`](#test_scoring_policy--test_invalid_policy_cannot_be_activated)
- [`test_risk_factors.py::test_increasing_factor_weights_can_block_a_transaction`](#test_risk_factors--test_increasing_factor_weights_can_block_a_transaction)
- [`test_risk_factors.py::test_invalid_factor_weight`](#test_risk_factors--test_invalid_factor_weight)
- [`test_risk_factors.py::test_every_rule_references_a_valid_factor`](#test_risk_factors--test_every_rule_references_a_valid_factor)
- [`test_risk_factors.py::test_load_partial_policy_and_default_configuration`](#test_risk_factors--test_load_partial_policy_and_default_configuration)
- [`test_risk_factors.py::test_invalid_file_cannot_be_activated`](#test_risk_factors--test_invalid_file_cannot_be_activated)
- [`test_contextual_trust.py::test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar`](#test_contextual_trust--test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar)
- [`test_contextual_trust.py::test_invalid_contextual_policy_fails_before_accepting_requests`](#test_contextual_trust--test_invalid_contextual_policy_fails_before_accepting_requests)
- [`test_account_untrust.py::test_disabled_account_control_ignores_history_and_current_evidence`](#test_account_untrust--test_disabled_account_control_ignores_history_and_current_evidence)
- [`test_account_untrust.py::test_invalid_untrust_policy_fails_startup`](#test_account_untrust--test_invalid_untrust_policy_fails_startup)
- [`test_untrust_contrasts.py::test_reclassifying_a_noneligible_rule_does_not_create_suspicion`](#test_untrust_contrasts--test_reclassifying_a_noneligible_rule_does_not_create_suspicion)
- [`test_entity_risk.py::test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields`](#test_entity_risk--test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields)
- [`test_entity_risk.py::test_registry_loading_is_strict_hashed_and_off_is_explicit`](#test_entity_risk--test_registry_loading_is_strict_hashed_and_off_is_explicit)
- [`test_temporal_live.py::test_unvalidated_v2_contribution_cannot_be_enabled_accidentally`](#test_temporal_live--test_unvalidated_v2_contribution_cannot_be_enabled_accidentally)

<a id="cobertura-p05"></a>

### P05 — Confiança contextual

- [`test_contextual_trust.py::test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence`](#test_contextual_trust--test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence)
- [`test_contextual_trust.py::test_insufficient_or_invalid_evidence_cannot_grant_attenuation`](#test_contextual_trust--test_insufficient_or_invalid_evidence_cannot_grant_attenuation)
- [`test_contextual_trust.py::test_relationship_compatibility_boundaries_are_inclusive_and_exact`](#test_contextual_trust--test_relationship_compatibility_boundaries_are_inclusive_and_exact)
- [`test_contextual_trust.py::test_familiar_relationship_never_neutralizes_independent_controls`](#test_contextual_trust--test_familiar_relationship_never_neutralizes_independent_controls)
- [`test_contextual_trust.py::test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar`](#test_contextual_trust--test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar)
- [`test_contextual_trust.py::test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust`](#test_contextual_trust--test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust)
- [`test_contextual_trust.py::test_invalid_contextual_policy_fails_before_accepting_requests`](#test_contextual_trust--test_invalid_contextual_policy_fails_before_accepting_requests)
- [`test_contextual_trust_db.py::test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals`](#test_contextual_trust_db--test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals)
- [`test_contextual_trust_db.py::test_backdated_requests_received_on_one_day_cannot_manufacture_trust`](#test_contextual_trust_db--test_backdated_requests_received_on_one_day_cannot_manufacture_trust)
- [`test_contextual_trust_db.py::test_contextual_decision_is_persisted_and_retry_and_get_preserve_it`](#test_contextual_trust_db--test_contextual_decision_is_persisted_and_retry_and_get_preserve_it)
- [`test_contextual_trust_db.py::test_post_get_and_retry_preserve_contextual_response_without_duplicating_history`](#test_contextual_trust_db--test_post_get_and_retry_preserve_contextual_response_without_duplicating_history)

<a id="cobertura-p06"></a>

### P06 — Suspeita própria da conta

- [`test_duplicate_payment.py::test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust`](#test_duplicate_payment--test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust)
- [`test_contextual_trust.py::test_destination_evidence_intervenes_without_accusing_the_sender`](#test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender)
- [`test_contextual_trust.py::test_mixed_sender_and_destination_evidence_preserves_only_own_increment`](#test_contextual_trust--test_mixed_sender_and_destination_evidence_preserves_only_own_increment)
- [`test_contextual_trust.py::test_hypothetical_critical_destination_detector_cannot_create_own_risk`](#test_contextual_trust--test_hypothetical_critical_destination_detector_cannot_create_own_risk)
- [`test_contextual_trust_db.py::test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk`](#test_contextual_trust_db--test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk)
- [`test_contextual_trust_db.py::test_destination_attempts_remain_in_history_without_tainting_normal_next_payment`](#test_contextual_trust_db--test_destination_attempts_remain_in_history_without_tainting_normal_next_payment)
- [`test_account_untrust.py::test_increment_uses_current_rule_evidence_and_never_account_score`](#test_account_untrust--test_increment_uses_current_rule_evidence_and_never_account_score)
- [`test_account_untrust.py::test_account_thresholds_and_repeated_evidence_guard`](#test_account_untrust--test_account_thresholds_and_repeated_evidence_guard)
- [`test_account_untrust.py::test_active_block_does_not_refresh_itself_even_on_velocity_risk`](#test_account_untrust--test_active_block_does_not_refresh_itself_even_on_velocity_risk)
- [`test_account_untrust.py::test_first_transaction_and_account_age_alone_do_not_build_untrust`](#test_account_untrust--test_first_transaction_and_account_age_alone_do_not_build_untrust)
- [`test_account_untrust.py::test_single_low_risk_novelty_does_not_accumulate`](#test_account_untrust--test_single_low_risk_novelty_does_not_accumulate)
- [`test_account_untrust.py::test_disabled_account_control_ignores_history_and_current_evidence`](#test_account_untrust--test_disabled_account_control_ignores_history_and_current_evidence)
- [`test_account_untrust.py::test_notification_indicates_threshold_crossing_without_claiming_delivery`](#test_account_untrust--test_notification_indicates_threshold_crossing_without_claiming_delivery)
- [`test_account_untrust.py::test_invalid_untrust_policy_fails_startup`](#test_account_untrust--test_invalid_untrust_policy_fails_startup)
- [`test_account_untrust.py::test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score`](#test_account_untrust--test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score)
- [`test_account_untrust.py::test_untrust_is_per_account_not_all_accounts_of_same_owner`](#test_account_untrust--test_untrust_is_per_account_not_all_accounts_of_same_owner)
- [`test_account_untrust.py::test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points`](#test_account_untrust--test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points)
- [`test_account_untrust.py::test_concurrent_account_attempts_cannot_lose_increments`](#test_account_untrust--test_concurrent_account_attempts_cannot_lose_increments)
- [`test_account_untrust.py::test_server_clock_not_caller_event_time_is_passed_to_account_history`](#test_account_untrust--test_server_clock_not_caller_event_time_is_passed_to_account_history)
- [`test_account_untrust.py::test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control`](#test_account_untrust--test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control)
- [`test_account_untrust_db.py::test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts`](#test_account_untrust_db--test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts)
- [`test_untrust_contrasts.py::test_same_request_different_context_has_a_specific_cause`](#test_untrust_contrasts--test_same_request_different_context_has_a_specific_cause)
- [`test_untrust_contrasts.py::test_identical_clean_pix_changes_only_because_of_accumulated_evidence`](#test_untrust_contrasts--test_identical_clean_pix_changes_only_because_of_accumulated_evidence)
- [`test_untrust_contrasts.py::test_correlated_device_signals_accumulate_only_the_capped_contribution`](#test_untrust_contrasts--test_correlated_device_signals_accumulate_only_the_capped_contribution)
- [`test_untrust_contrasts.py::test_reclassifying_a_noneligible_rule_does_not_create_suspicion`](#test_untrust_contrasts--test_reclassifying_a_noneligible_rule_does_not_create_suspicion)
- [`test_untrust_contrasts.py::test_reclassifying_real_profile_evidence_does_not_erase_suspicion`](#test_untrust_contrasts--test_reclassifying_real_profile_evidence_does_not_erase_suspicion)
- [`test_untrust_contrasts.py::test_temporal_observation_and_restriction_do_not_feed_own_increment`](#test_untrust_contrasts--test_temporal_observation_and_restriction_do_not_feed_own_increment)
- [`test_untrust_contrasts.py::test_irrelevant_request_changes_preserve_decision_and_suspicion`](#test_untrust_contrasts--test_irrelevant_request_changes_preserve_decision_and_suspicion)
- [`test_untrust_replay.py::test_replay_agrees_with_persisted_decisions_at_each_step`](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step)
- [`test_untrust_replay.py::test_comparison_report_attributes_the_same_pix_change_to_its_account_history`](#test_untrust_replay--test_comparison_report_attributes_the_same_pix_change_to_its_account_history)
- [`test_entity_risk.py::test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores`](#test_entity_risk--test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores)
- [`test_entity_risk.py::test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded`](#test_entity_risk--test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded)
- [`test_entity_risk_db.py::test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score`](#test_entity_risk_db--test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score)
- [`test_temporal_live.py::test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis`](#test_temporal_live--test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis)
- [`test_temporal_live_db.py::test_own_history_uses_received_window_and_rejects_legacy_evidence`](#test_temporal_live_db--test_own_history_uses_received_window_and_rejects_legacy_evidence)
- [`test_metadata.py::test_rule_names_explain_accumulated_risk_overrides`](#test_metadata--test_rule_names_explain_accumulated_risk_overrides)
- [`test_history_audit.py::test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls`](#test_history_audit--test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls)

<a id="cobertura-p07"></a>

### P07 — Titular e vínculos

- [`test_contextual_trust_db.py::test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk`](#test_contextual_trust_db--test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk)
- [`test_account_untrust.py::test_untrust_is_per_account_not_all_accounts_of_same_owner`](#test_account_untrust--test_untrust_is_per_account_not_all_accounts_of_same_owner)
- [`test_entity_risk.py::test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct`](#test_entity_risk--test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct)
- [`test_entity_risk.py::test_new_company_inherits_exposure_through_verified_common_controller`](#test_entity_risk--test_new_company_inherits_exposure_through_verified_common_controller)
- [`test_entity_risk.py::test_multiple_company_levels_and_cycles_do_not_duplicate_events`](#test_entity_risk--test_multiple_company_levels_and_cycles_do_not_duplicate_events)
- [`test_entity_risk.py::test_same_incident_across_ten_cnpjs_is_one_independent_evidence`](#test_entity_risk--test_same_incident_across_ten_cnpjs_is_one_independent_evidence)
- [`test_entity_risk.py::test_company_branches_are_one_company_root_not_ten_companies`](#test_entity_risk--test_company_branches_are_one_company_root_not_ten_companies)
- [`test_entity_risk.py::test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override`](#test_entity_risk--test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override)
- [`test_entity_risk.py::test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud`](#test_entity_risk--test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud)
- [`test_entity_risk.py::test_incident_must_be_known_active_and_not_revoked_at_decision`](#test_entity_risk--test_incident_must_be_known_active_and_not_revoked_at_decision)
- [`test_entity_risk.py::test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation`](#test_entity_risk--test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation)
- [`test_entity_risk.py::test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores`](#test_entity_risk--test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores)
- [`test_entity_risk.py::test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded`](#test_entity_risk--test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded)
- [`test_entity_risk.py::test_rule_evidence_from_before_ownership_does_not_create_soft_exposure`](#test_entity_risk--test_rule_evidence_from_before_ownership_does_not_create_soft_exposure)
- [`test_entity_risk.py::test_clean_companies_do_not_dilute_high_risk_company`](#test_entity_risk--test_clean_companies_do_not_dilute_high_risk_company)
- [`test_entity_risk.py::test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works`](#test_entity_risk--test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works)
- [`test_entity_risk.py::test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence`](#test_entity_risk--test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence)
- [`test_entity_risk.py::test_shadow_preserves_scores_decision_and_account_evidence`](#test_entity_risk--test_shadow_preserves_scores_decision_and_account_evidence)
- [`test_entity_risk.py::test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence`](#test_entity_risk--test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence)
- [`test_entity_risk.py::test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved`](#test_entity_risk--test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved)
- [`test_entity_risk.py::test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields`](#test_entity_risk--test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields)
- [`test_entity_risk.py::test_registry_loading_is_strict_hashed_and_off_is_explicit`](#test_entity_risk--test_registry_loading_is_strict_hashed_and_off_is_explicit)
- [`test_entity_risk_db.py::test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score`](#test_entity_risk_db--test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score)
- [`test_entity_risk_db.py::test_controller_new_account_preserves_own_titular_risk_and_saved_decision`](#test_entity_risk_db--test_controller_new_account_preserves_own_titular_risk_and_saved_decision)
- [`test_entity_risk_db.py::test_confirmed_corporate_exposure_reaches_saved_controller_result`](#test_entity_risk_db--test_confirmed_corporate_exposure_reaches_saved_controller_result)
- [`test_temporal_live_db.py::test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay`](#test_temporal_live_db--test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay)
- [`test_metadata.py::test_rule_names_explain_accumulated_risk_overrides`](#test_metadata--test_rule_names_explain_accumulated_risk_overrides)

<a id="cobertura-p08"></a>

### P08 — Indicadores financeiros

- [`test_entity_risk_db.py::test_postgres_payment_query_includes_receipts_and_bounds_history`](#test_entity_risk_db--test_postgres_payment_query_includes_receipts_and_bounds_history)
- [`test_financial_features.py::test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted`](#test_financial_features--test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted)
- [`test_financial_features.py::test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy`](#test_financial_features--test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy)
- [`test_financial_features.py::test_future_old_rejected_and_self_transfers_do_not_create_exposure`](#test_financial_features--test_future_old_rejected_and_self_transfers_do_not_create_exposure)
- [`test_financial_features.py::test_truncation_and_unknown_counterparty_risk_are_explicit`](#test_financial_features--test_truncation_and_unknown_counterparty_risk_are_explicit)
- [`test_temporal_gnn.py::test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect`](#test_temporal_gnn--test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect)
- [`test_temporal_gnn.py::test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window`](#test_temporal_gnn--test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window)
- [`test_temporal_gnn.py::test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass`](#test_temporal_gnn--test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass)

<a id="cobertura-p09"></a>

### P09 — Grafo temporal v2

- [`test_untrust_contrasts.py::test_temporal_observation_and_restriction_do_not_feed_own_increment`](#test_untrust_contrasts--test_temporal_observation_and_restriction_do_not_feed_own_increment)
- [`test_temporal_live.py::test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history`](#test_temporal_live--test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history)
- [`test_temporal_live.py::test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis`](#test_temporal_live--test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis)
- [`test_temporal_live.py::test_missing_v2_model_has_explicit_zero_contribution`](#test_temporal_live--test_missing_v2_model_has_explicit_zero_contribution)
- [`test_temporal_live.py::test_unvalidated_v2_contribution_cannot_be_enabled_accidentally`](#test_temporal_live--test_unvalidated_v2_contribution_cannot_be_enabled_accidentally)
- [`test_temporal_live.py::test_incomplete_neighborhood_abstains_without_calling_model`](#test_temporal_live--test_incomplete_neighborhood_abstains_without_calling_model)
- [`test_temporal_live.py::test_invalid_prediction_does_not_escape_as_a_fraud_score`](#test_temporal_live--test_invalid_prediction_does_not_escape_as_a_fraud_score)
- [`test_temporal_live.py::test_high_v2_prediction_remains_observational`](#test_temporal_live--test_high_v2_prediction_remains_observational)
- [`test_temporal_live.py::test_http_v2_runs_by_default_and_saved_evidence_is_replayed`](#test_temporal_live--test_http_v2_runs_by_default_and_saved_evidence_is_replayed)
- [`test_temporal_live.py::test_bad_model_json_is_unavailable_without_breaking_startup`](#test_temporal_live--test_bad_model_json_is_unavailable_without_breaking_startup)
- [`test_temporal_live.py::test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](#test_temporal_live--test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions)
- [`test_temporal_live.py::test_disabled_or_unavailable_model_does_not_query_optional_history`](#test_temporal_live--test_disabled_or_unavailable_model_does_not_query_optional_history)
- [`test_temporal_live.py::test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis`](#test_temporal_live--test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis)
- [`test_temporal_live.py::test_model_prediction_failure_cannot_modify_or_break_rule_decision`](#test_temporal_live--test_model_prediction_failure_cannot_modify_or_break_rule_decision)
- [`test_temporal_live_db.py::test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood`](#test_temporal_live_db--test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood)
- [`test_temporal_live_db.py::test_own_history_uses_received_window_and_rejects_legacy_evidence`](#test_temporal_live_db--test_own_history_uses_received_window_and_rejects_legacy_evidence)
- [`test_temporal_live_db.py::test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample`](#test_temporal_live_db--test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample)
- [`test_temporal_live_db.py::test_legacy_payload_cannot_break_optional_v2_observation`](#test_temporal_live_db--test_legacy_payload_cannot_break_optional_v2_observation)
- [`test_temporal_live_db.py::test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay`](#test_temporal_live_db--test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay)
- [`test_gnn_http.py::test_shadow_v2_assessment_is_saved_and_replayed`](#test_gnn_http--test_shadow_v2_assessment_is_saved_and_replayed)
- [`test_gnn_http.py::test_future_cross_payer_history_cannot_influence_graph`](#test_gnn_http--test_future_cross_payer_history_cannot_influence_graph)
- [`test_temporal_case.py::test_export_contains_actual_nodes_edges_and_all_rule_results`](#test_temporal_case--test_export_contains_actual_nodes_edges_and_all_rule_results)
- [`test_temporal_case.py::test_v2_case_runs_through_database_decision_and_replay`](#test_temporal_case--test_v2_case_runs_through_database_decision_and_replay)
- [`test_temporal_gnn.py::test_payment_and_device_relations_are_separate_and_directional`](#test_temporal_gnn--test_payment_and_device_relations_are_separate_and_directional)
- [`test_temporal_gnn.py::test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect`](#test_temporal_gnn--test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect)
- [`test_temporal_gnn.py::test_holder_identity_deduplicates_accounts_on_a_shared_device`](#test_temporal_gnn--test_holder_identity_deduplicates_accounts_on_a_shared_device)
- [`test_temporal_gnn.py::test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window`](#test_temporal_gnn--test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window)
- [`test_temporal_gnn.py::test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass`](#test_temporal_gnn--test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass)
- [`test_temporal_gnn.py::test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact`](#test_temporal_gnn--test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact)
- [`test_temporal_gnn.py::test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak`](#test_temporal_gnn--test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak)
- [`test_temporal_gnn.py::test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge`](#test_temporal_gnn--test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge)
- [`test_temporal_gnn.py::test_truncated_conflicting_and_unbounded_history_are_refused`](#test_temporal_gnn--test_truncated_conflicting_and_unbounded_history_are_refused)
- [`test_temporal_gnn.py::test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction`](#test_temporal_gnn--test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction)
- [`test_temporal_gnn.py::test_exported_v2_is_safe_finite_and_permutation_invariant`](#test_temporal_gnn--test_exported_v2_is_safe_finite_and_permutation_invariant)
- [`test_temporal_gnn.py::test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics`](#test_temporal_gnn--test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics)
- [`test_gnn_validation.py::test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow`](#test_gnn_validation--test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow)
- [`test_gnn_validation.py::test_validation_uses_real_sql_without_persisting_synthetic_scenarios`](#test_gnn_validation--test_validation_uses_real_sql_without_persisting_synthetic_scenarios)
- [`test_metadata.py::test_public_graph_score_is_present_only_when_available`](#test_metadata--test_public_graph_score_is_present_only_when_available)

<a id="cobertura-p10"></a>

### P10 — Contrato e validação

- [`test_account_untrust.py::test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points`](#test_account_untrust--test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points)
- [`test_untrust_contrasts.py::test_irrelevant_request_changes_preserve_decision_and_suspicion`](#test_untrust_contrasts--test_irrelevant_request_changes_preserve_decision_and_suspicion)
- [`test_gnn_validation.py::test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account`](#test_gnn_validation--test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account)
- [`test_pix.py::test_equivalent_timezone_and_document_format_replay`](#test_pix--test_equivalent_timezone_and_document_format_replay)
- [`test_pix.py::test_missing_geolocation_is_valid`](#test_pix--test_missing_geolocation_is_valid)
- [`test_pix.py::test_cnpj_is_valid`](#test_pix--test_cnpj_is_valid)
- [`test_pix.py::test_invalid_payload_is_rejected_without_consuming_id`](#test_pix--test_invalid_payload_is_rejected_without_consuming_id)
- [`test_pix.py::test_required_and_unknown_fields`](#test_pix--test_required_and_unknown_fields)
- [`test_pix.py::test_missing_transaction`](#test_pix--test_missing_transaction)
- [`test_pix.py::test_public_health_and_openapi`](#test_pix--test_public_health_and_openapi)
- [`test_api_security.py::test_oversized_http_request_does_not_consume_transaction_id`](#test_api_security--test_oversized_http_request_does_not_consume_transaction_id)

<a id="cobertura-p11"></a>

### P11 — Idempotência e concorrência

- [`test_no_history.py::test_first_pix_http_boundary_and_replay`](#test_no_history--test_first_pix_http_boundary_and_replay)
- [`test_no_history.py::test_policy_change_does_not_recompute_a_saved_first_pix`](#test_no_history--test_policy_change_does_not_recompute_a_saved_first_pix)
- [`test_duplicate_payment.py::test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed`](#test_duplicate_payment--test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed)
- [`test_duplicate_payment.py::test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent`](#test_duplicate_payment--test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent)
- [`test_access_patterns.py::test_shared_device_concurrency_sees_prior_commits`](#test_access_patterns--test_shared_device_concurrency_sees_prior_commits)
- [`test_risk_score.py::test_first_pix_requests_two_factor_and_saves_explanation`](#test_risk_score--test_first_pix_requests_two_factor_and_saves_explanation)
- [`test_contextual_trust_db.py::test_contextual_decision_is_persisted_and_retry_and_get_preserve_it`](#test_contextual_trust_db--test_contextual_decision_is_persisted_and_retry_and_get_preserve_it)
- [`test_contextual_trust_db.py::test_post_get_and_retry_preserve_contextual_response_without_duplicating_history`](#test_contextual_trust_db--test_post_get_and_retry_preserve_contextual_response_without_duplicating_history)
- [`test_account_untrust.py::test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score`](#test_account_untrust--test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score)
- [`test_account_untrust.py::test_concurrent_account_attempts_cannot_lose_increments`](#test_account_untrust--test_concurrent_account_attempts_cannot_lose_increments)
- [`test_untrust_replay.py::test_replay_agrees_with_persisted_decisions_at_each_step`](#test_untrust_replay--test_replay_agrees_with_persisted_decisions_at_each_step)
- [`test_untrust_replay.py::test_replay_rejects_conflicting_ids_instead_of_recounting_risk`](#test_untrust_replay--test_replay_rejects_conflicting_ids_instead_of_recounting_risk)
- [`test_entity_risk_db.py::test_controller_new_account_preserves_own_titular_risk_and_saved_decision`](#test_entity_risk_db--test_controller_new_account_preserves_own_titular_risk_and_saved_decision)
- [`test_temporal_live.py::test_http_v2_runs_by_default_and_saved_evidence_is_replayed`](#test_temporal_live--test_http_v2_runs_by_default_and_saved_evidence_is_replayed)
- [`test_temporal_live_db.py::test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay`](#test_temporal_live_db--test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay)
- [`test_gnn_http.py::test_shadow_v2_assessment_is_saved_and_replayed`](#test_gnn_http--test_shadow_v2_assessment_is_saved_and_replayed)
- [`test_temporal_case.py::test_v2_case_runs_through_database_decision_and_replay`](#test_temporal_case--test_v2_case_runs_through_database_decision_and_replay)
- [`test_graph_untrust_experiment.py::test_replay_deduplicates_retries_and_excludes_future_and_candidate`](#test_graph_untrust_experiment--test_replay_deduplicates_retries_and_excludes_future_and_candidate)
- [`test_gnn_validation.py::test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow`](#test_gnn_validation--test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow)
- [`test_pix.py::test_retries_do_not_inflate_velocity`](#test_pix--test_retries_do_not_inflate_velocity)
- [`test_pix.py::test_changed_payload_conflicts_and_preserves_original`](#test_pix--test_changed_payload_conflicts_and_preserves_original)
- [`test_pix.py::test_equivalent_timezone_and_document_format_replay`](#test_pix--test_equivalent_timezone_and_document_format_replay)
- [`test_pix.py::test_concurrent_retries_share_one_analysis`](#test_pix--test_concurrent_retries_share_one_analysis)
- [`test_pix.py::test_concurrent_distinct_pix_cannot_bypass_velocity`](#test_pix--test_concurrent_distinct_pix_cannot_bypass_velocity)
- [`test_pix.py::test_same_id_different_payers_cannot_overwrite`](#test_pix--test_same_id_different_payers_cannot_overwrite)
- [`test_metadata.py::test_minimal_http_response_details_and_saved_audit`](#test_metadata--test_minimal_http_response_details_and_saved_audit)
- [`test_metadata.py::test_processing_timer_covers_analysis_and_is_not_recomputed`](#test_metadata--test_processing_timer_covers_analysis_and_is_not_recomputed)
- [`test_history_audit.py::test_committed_payload_and_evidence_survive_new_connection`](#test_history_audit--test_committed_payload_and_evidence_survive_new_connection)

<a id="cobertura-p12"></a>

### P12 — Auditoria e explicabilidade

- [`test_no_history.py::test_policy_change_does_not_recompute_a_saved_first_pix`](#test_no_history--test_policy_change_does_not_recompute_a_saved_first_pix)
- [`test_duplicate_payment.py::test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed`](#test_duplicate_payment--test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed)
- [`test_risk_score.py::test_first_pix_requests_two_factor_and_saves_explanation`](#test_risk_score--test_first_pix_requests_two_factor_and_saves_explanation)
- [`test_risk_score.py::test_factor_sum_can_exceed_final_score_cap`](#test_risk_score--test_factor_sum_can_exceed_final_score_cap)
- [`test_contextual_trust.py::test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence`](#test_contextual_trust--test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence)
- [`test_contextual_trust.py::test_destination_evidence_intervenes_without_accusing_the_sender`](#test_contextual_trust--test_destination_evidence_intervenes_without_accusing_the_sender)
- [`test_contextual_trust.py::test_hypothetical_critical_destination_detector_cannot_create_own_risk`](#test_contextual_trust--test_hypothetical_critical_destination_detector_cannot_create_own_risk)
- [`test_contextual_trust_db.py::test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk`](#test_contextual_trust_db--test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk)
- [`test_contextual_trust_db.py::test_contextual_decision_is_persisted_and_retry_and_get_preserve_it`](#test_contextual_trust_db--test_contextual_decision_is_persisted_and_retry_and_get_preserve_it)
- [`test_contextual_trust_db.py::test_post_get_and_retry_preserve_contextual_response_without_duplicating_history`](#test_contextual_trust_db--test_post_get_and_retry_preserve_contextual_response_without_duplicating_history)
- [`test_entity_risk.py::test_registry_loading_is_strict_hashed_and_off_is_explicit`](#test_entity_risk--test_registry_loading_is_strict_hashed_and_off_is_explicit)
- [`test_entity_risk_db.py::test_confirmed_corporate_exposure_reaches_saved_controller_result`](#test_entity_risk_db--test_confirmed_corporate_exposure_reaches_saved_controller_result)
- [`test_temporal_live.py::test_http_v2_runs_by_default_and_saved_evidence_is_replayed`](#test_temporal_live--test_http_v2_runs_by_default_and_saved_evidence_is_replayed)
- [`test_gnn_http.py::test_shadow_v2_assessment_is_saved_and_replayed`](#test_gnn_http--test_shadow_v2_assessment_is_saved_and_replayed)
- [`test_temporal_case.py::test_export_contains_actual_nodes_edges_and_all_rule_results`](#test_temporal_case--test_export_contains_actual_nodes_edges_and_all_rule_results)
- [`test_pix.py::test_sixth_attempt_is_rejected_and_rejections_are_saved`](#test_pix--test_sixth_attempt_is_rejected_and_rejections_are_saved)
- [`test_metadata.py::test_minimal_http_response_details_and_saved_audit`](#test_metadata--test_minimal_http_response_details_and_saved_audit)
- [`test_metadata.py::test_hard_limit_has_readable_rule_name`](#test_metadata--test_hard_limit_has_readable_rule_name)
- [`test_metadata.py::test_approved_http_response_has_empty_rules_only_when_requested`](#test_metadata--test_approved_http_response_has_empty_rules_only_when_requested)
- [`test_metadata.py::test_processing_timer_covers_analysis_and_is_not_recomputed`](#test_metadata--test_processing_timer_covers_analysis_and_is_not_recomputed)
- [`test_metadata.py::test_legacy_summary_does_not_change_evidence`](#test_metadata--test_legacy_summary_does_not_change_evidence)
- [`test_metadata.py::test_factor_list_and_uncapped_sum_stay_internal`](#test_metadata--test_factor_list_and_uncapped_sum_stay_internal)
- [`test_metadata.py::test_all_current_rules_have_readable_aliases`](#test_metadata--test_all_current_rules_have_readable_aliases)
- [`test_metadata.py::test_public_graph_score_is_present_only_when_available`](#test_metadata--test_public_graph_score_is_present_only_when_available)
- [`test_metadata.py::test_details_only_list_effective_rules_and_mandatory_controls`](#test_metadata--test_details_only_list_effective_rules_and_mandatory_controls)
- [`test_metadata.py::test_rule_names_explain_accumulated_risk_overrides`](#test_metadata--test_rule_names_explain_accumulated_risk_overrides)
- [`test_metadata.py::test_no_rules_returns_empty_details_instead_of_a_no_rule_alias`](#test_metadata--test_no_rules_returns_empty_details_instead_of_a_no_rule_alias)
- [`test_history_audit.py::test_database_refuses_history_mutation`](#test_history_audit--test_database_refuses_history_mutation)
- [`test_history_audit.py::test_committed_payload_and_evidence_survive_new_connection`](#test_history_audit--test_committed_payload_and_evidence_survive_new_connection)

<a id="cobertura-p13"></a>

### P13 — Proteções HTTP

- [`test_temporal_live.py::test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis`](#test_temporal_live--test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis)
- [`test_pix.py::test_business_endpoints_accept_requests_without_internal_token`](#test_pix--test_business_endpoints_accept_requests_without_internal_token)
- [`test_pix.py::test_public_health_and_openapi`](#test_pix--test_public_health_and_openapi)
- [`test_api_security.py::test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length`](#test_api_security--test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length)
- [`test_api_security.py::test_exact_size_limit_preserves_body_for_validation`](#test_api_security--test_exact_size_limit_preserves_body_for_validation)
- [`test_api_security.py::test_pix_requires_json_content_type`](#test_api_security--test_pix_requires_json_content_type)
- [`test_api_security.py::test_malformed_content_length_is_rejected`](#test_api_security--test_malformed_content_length_is_rejected)
- [`test_api_security.py::test_body_read_has_total_deadline`](#test_api_security--test_body_read_has_total_deadline)
- [`test_api_security.py::test_request_without_internal_token_reaches_endpoint_and_sets_security_headers`](#test_api_security--test_request_without_internal_token_reaches_endpoint_and_sets_security_headers)
- [`test_api_security.py::test_unhandled_error_does_not_leak_exception_details_and_is_correlated`](#test_api_security--test_unhandled_error_does_not_leak_exception_details_and_is_correlated)
- [`test_api_security.py::test_success_and_not_found_http_responses_prohibit_caching`](#test_api_security--test_success_and_not_found_http_responses_prohibit_caching)
- [`test_api_security.py::test_oversized_http_request_does_not_consume_transaction_id`](#test_api_security--test_oversized_http_request_does_not_consume_transaction_id)

<a id="cobertura-p14"></a>

### P14 — Validação experimental

- [`test_untrust_replay.py::test_comparison_report_attributes_the_same_pix_change_to_its_account_history`](#test_untrust_replay--test_comparison_report_attributes_the_same_pix_change_to_its_account_history)
- [`test_temporal_case.py::test_export_contains_actual_nodes_edges_and_all_rule_results`](#test_temporal_case--test_export_contains_actual_nodes_edges_and_all_rule_results)
- [`test_temporal_case.py::test_v2_case_runs_through_database_decision_and_replay`](#test_temporal_case--test_v2_case_runs_through_database_decision_and_replay)
- [`test_temporal_gnn.py::test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak`](#test_temporal_gnn--test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak)
- [`test_temporal_gnn.py::test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction`](#test_temporal_gnn--test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction)
- [`test_temporal_gnn.py::test_synthetic_split_dates_and_openings_are_valid`](#test_temporal_gnn--test_synthetic_split_dates_and_openings_are_valid)
- [`test_temporal_gnn.py::test_exported_v2_is_safe_finite_and_permutation_invariant`](#test_temporal_gnn--test_exported_v2_is_safe_finite_and_permutation_invariant)
- [`test_temporal_gnn.py::test_comparison_selects_on_validation_and_records_parity_for_every_seed`](#test_temporal_gnn--test_comparison_selects_on_validation_and_records_parity_for_every_seed)
- [`test_temporal_gnn.py::test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget`](#test_temporal_gnn--test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget)
- [`test_temporal_gnn.py::test_threshold_does_not_split_tied_legitimate_and_fraud_scores`](#test_temporal_gnn--test_threshold_does_not_split_tied_legitimate_and_fraud_scores)
- [`test_temporal_gnn.py::test_entity_identities_do_not_overlap_across_training_validation_and_test`](#test_temporal_gnn--test_entity_identities_do_not_overlap_across_training_validation_and_test)
- [`test_graph_untrust_experiment.py::test_two_hops_finds_independent_evidence_without_counting_paths_or_root`](#test_graph_untrust_experiment--test_two_hops_finds_independent_evidence_without_counting_paths_or_root)
- [`test_graph_untrust_experiment.py::test_future_and_expired_evidence_do_not_increase_current_risk`](#test_graph_untrust_experiment--test_future_and_expired_evidence_do_not_increase_current_risk)
- [`test_graph_untrust_experiment.py::test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy`](#test_graph_untrust_experiment--test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy)
- [`test_graph_untrust_experiment.py::test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages`](#test_graph_untrust_experiment--test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages)
- [`test_graph_untrust_experiment.py::test_neighbor_budget_keeps_latest_contacts_and_bounds_search`](#test_graph_untrust_experiment--test_neighbor_budget_keeps_latest_contacts_and_bounds_search)
- [`test_graph_untrust_experiment.py::test_repass_requires_distinct_receipts_time_order_value_and_different_destination`](#test_graph_untrust_experiment--test_repass_requires_distinct_receipts_time_order_value_and_different_destination)
- [`test_graph_untrust_experiment.py::test_replay_deduplicates_retries_and_excludes_future_and_candidate`](#test_graph_untrust_experiment--test_replay_deduplicates_retries_and_excludes_future_and_candidate)
- [`test_graph_untrust_experiment.py::test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate`](#test_graph_untrust_experiment--test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate)
- [`test_graph_untrust_experiment.py::test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint`](#test_graph_untrust_experiment--test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint)
- [`test_graph_untrust_experiment.py::test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly`](#test_graph_untrust_experiment--test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly)
- [`test_gnn_validation.py::test_candidate_never_relaxes_or_escalates_an_existing_intervention`](#test_gnn_validation--test_candidate_never_relaxes_or_escalates_an_existing_intervention)
- [`test_gnn_validation.py::test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs`](#test_gnn_validation--test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs)
- [`test_gnn_validation.py::test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score`](#test_gnn_validation--test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score)
- [`test_gnn_validation.py::test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases`](#test_gnn_validation--test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases)
- [`test_gnn_validation.py::test_calibration_without_both_classes_disables_proposals`](#test_gnn_validation--test_calibration_without_both_classes_disables_proposals)
- [`test_gnn_validation.py::test_report_separates_false_alarm_rate_from_incremental_legitimate_friction`](#test_gnn_validation--test_report_separates_false_alarm_rate_from_incremental_legitimate_friction)
- [`test_gnn_validation.py::test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget`](#test_gnn_validation--test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget)
- [`test_gnn_validation.py::test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account`](#test_gnn_validation--test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account)
- [`test_gnn_validation.py::test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow`](#test_gnn_validation--test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow)
- [`test_gnn_validation.py::test_validation_uses_real_sql_without_persisting_synthetic_scenarios`](#test_gnn_validation--test_validation_uses_real_sql_without_persisting_synthetic_scenarios)

## Alcance e limites da evidência

- O inventário cobre todas as funções `test_*` dos arquivos atuais `tests/test_*.py`; fixtures e auxiliares são infraestrutura, não testes adicionais.
- Há variações positivas/negativas para as 13 regras; a matriz não afirma cobertura de todas as combinações possíveis nem cobertura percentual de linhas.
- Testes sintéticos e relatórios salvos não comprovam taxa real de fraude, falsos positivos, liquidação ou sucesso de 2FA.
- O detector crítico de destino de `test_contextual_trust.py` é uma injeção exclusiva do teste; não demonstra blacklist externa implementada.
- O teste de expiração por conta insere 40 pontos como fixture de consulta; o motor limita cada incremento novo a 25.
- O experimento heurístico offline pode diluir sinais por contatos limpos; `entity_risk` usa máximo/corroboração. São políticas diferentes e não devem ser confundidas.
- O teste de falha SQL temporal comprova propagação e ausência de commit; não exercita o handler HTTP 503. O teste de readiness cobre o caso positivo.
- O v2 permanece observacional; uma proposta experimental de 2FA e sua aprovação numérica não habilitam contribuição automaticamente.

## Conferência documental

Correspondência conferida por análise AST: 28 arquivos, 230 funções, 544 casos expandidos, sem função ausente, duplicada ou documentada sem existir. Os links de função usam a linha de definição observada nesta revisão. Contagens e linhas devem ser revisadas quando a suíte mudar.
