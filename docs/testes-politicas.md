# Inventário vigente de testes e políticas

Política `pix-score-v9`. Coleta real em 18/10/2026: **30 arquivos,
259 funções e 691 casos** após parametrização. Fonte: `pytest --collect-only -q`.
Não há soma de contagens de revisões diferentes. As funções abaixo correspondem
ao código atual e têm links para suas linhas de definição.

## Execução

A coleta identifica casos; aprovação exige execução. Os comandos completos e o
projeto Compose isolado estão no [README](../README.md#testes-e-limites-da-avaliação).
Execução em 18/10/2026 no projeto isolado `pix-docs-audit`, com GNN padrão
`contribute`: **691 aprovados em 26,44s, sem falhas ou casos ignorados**.
`ruff check src tests scripts` passou; `ruff format --check src tests scripts`
confirmou os **84 arquivos Python** formatados. A limpeza dos artefatos foi
incluída na imagem testada; o código da aplicação e dos testes foi preservado.

Testes unitários usam histórico fornecido/mocks; ASGI local testa transporte em
memória. Testes PostgreSQL/HTTP precisam de API e banco. Sem
`PIX_TEST_DATABASE_URL`, a fixture `database_engine` ignora casos dependentes;
outros testes HTTP ainda podem precisar da API. A fixture `api` compara o resumo
HTTP com a auditoria persistida e só então entrega o DTO interno às asserções.

Os avaliadores SQL descartam cenários por transação externa; os testes HTTP usam
IDs/documentos únicos e podem gravar dados sintéticos. Use banco separado.
Testes `shadow` e comparadores fixos verificam modos/referências explícitos;
não alteram o padrão `contribute` da API. Testes de replay de políticas anteriores
verificam compatibilidade de decisões imutáveis, sem reativar implementação antiga.

<a id="matriz-politicas-testes"></a>

## Matriz de políticas e testes

Os códigos são definidos em [políticas de negócio](politicas-negocio.md).
O vínculo abaixo indica o tema da suíte; não afirma que cada função verifica
todas as políticas listadas.

| Arquivo | Casos coletados | Tema | Políticas |
|---|---:|---|---|
| [test_access_patterns.py](#test_access_patterns) | 25 | Aparelhos, canal e horário | R09–R12, P03 |
| [test_account_untrust.py](#test_account_untrust) | 35 | Incremento e restrição própria | P06 |
| [test_account_untrust_db.py](#test_account_untrust_db) | 1 | Expiração e persistência do acumulado | P06, P11 |
| [test_api_security.py](#test_api_security) | 17 | Transporte, headers e erros | P10, P13 |
| [test_contextual_trust.py](#test_contextual_trust) | 25 | Atenuação e atribuição própria | P05, P06 |
| [test_contextual_trust_db.py](#test_contextual_trust_db) | 6 | Amostras e relógios no banco | P03, P05, P06 |
| [test_duplicate_payment.py](#test_duplicate_payment) | 22 | Possível duplicidade | R13, P11 |
| [test_dynamic_profile.py](#test_dynamic_profile) | 18 | Perfil somente por aprovações | R08, P03 |
| [test_entity_risk.py](#test_entity_risk) | 28 | Titular, vínculos e ocorrências | P07 |
| [test_entity_risk_db.py](#test_entity_risk_db) | 4 | Histórico real do titular | P07, P11 |
| [test_financial_features.py](#test_financial_features) | 4 | Recebimentos e repasses | P08 |
| [test_gnn_contribution.py](#test_gnn_contribution) | 45 | Contribuição ativa, manifesto e replay | P01, P04, P09, P11, P12 |
| [test_gnn_false_positives.py](#test_gnn_false_positives) | 102 | Negativos difíceis, calibração e artefatos | P09, P14 |
| [test_gnn_http.py](#test_gnn_http) | 2 | Resumo HTTP do grafo | P09, P10, P12 |
| [test_gnn_validation.py](#test_gnn_validation) | 20 | Propostas e critérios de avaliação | P14 |
| [test_graph_untrust_experiment.py](#test_graph_untrust_experiment) | 27 | Heurísticas de vizinhança offline | P14 |
| [test_history_audit.py](#test_history_audit) | 13 | Elegibilidade e imutabilidade | P03, P11, P12 |
| [test_metadata.py](#test_metadata) | 21 | Resumo público e auditoria interna | P10, P12 |
| [test_no_history.py](#test_no_history) | 28 | Piso de R$ 500 e replay de política | R03, R04, P03, P11 |
| [test_pix.py](#test_pix) | 43 | Contrato, histórico e concorrência | P03, P10, P11 |
| [test_risk_factors.py](#test_risk_factors) | 19 | Pesos, fatores e configuração | P02, P04 |
| [test_risk_score.py](#test_risk_score) | 9 | Resultados integrados das regras | P01, P02 |
| [test_rule_audit.py](#test_rule_audit) | 47 | Fronteiras das 13 regras | R01–R13, P01, P02 |
| [test_scoring_policy.py](#test_scoring_policy) | 27 | Prioridade, limiares e limites fortes | P01, P02, P04 |
| [test_temporal_case.py](#test_temporal_case) | 2 | Caso temporal completo e SQL | P09, P11, P14 |
| [test_temporal_gnn.py](#test_temporal_gnn) | 29 | Schema, atributos, pesos e paridade | P09, P14 |
| [test_temporal_live.py](#test_temporal_live) | 30 | Inferência, abstenção e modos | P09, P10, P11 |
| [test_temporal_live_db.py](#test_temporal_live_db) | 10 | Vizinhança e relógios reais | P03, P07, P09 |
| [test_untrust_contrasts.py](#test_untrust_contrasts) | 16 | Invariâncias e causas de intervenção | P01, P06 |
| [test_untrust_replay.py](#test_untrust_replay) | 16 | Equivalência offline/PostgreSQL | P03, P05, P06, P11 |

As regras R01–R13 têm fronteiras individuais em `test_rule_audit.py`.

<a id="cobertura-p01"></a>

**P01** — [test_gnn_contribution.py](#test_gnn_contribution), [test_risk_score.py](#test_risk_score), [test_rule_audit.py](#test_rule_audit), [test_scoring_policy.py](#test_scoring_policy), [test_untrust_contrasts.py](#test_untrust_contrasts).

<a id="cobertura-p02"></a>

**P02** — [test_risk_factors.py](#test_risk_factors), [test_risk_score.py](#test_risk_score), [test_rule_audit.py](#test_rule_audit), [test_scoring_policy.py](#test_scoring_policy).

<a id="cobertura-p03"></a>

**P03** — [test_access_patterns.py](#test_access_patterns), [test_contextual_trust_db.py](#test_contextual_trust_db), [test_dynamic_profile.py](#test_dynamic_profile), [test_history_audit.py](#test_history_audit), [test_no_history.py](#test_no_history), [test_pix.py](#test_pix), [test_temporal_live_db.py](#test_temporal_live_db), [test_untrust_replay.py](#test_untrust_replay).

<a id="cobertura-p04"></a>

**P04** — [test_gnn_contribution.py](#test_gnn_contribution), [test_risk_factors.py](#test_risk_factors), [test_scoring_policy.py](#test_scoring_policy).

<a id="cobertura-p05"></a>

**P05** — [test_contextual_trust.py](#test_contextual_trust), [test_contextual_trust_db.py](#test_contextual_trust_db), [test_untrust_replay.py](#test_untrust_replay).

<a id="cobertura-p06"></a>

**P06** — [test_account_untrust.py](#test_account_untrust), [test_account_untrust_db.py](#test_account_untrust_db), [test_contextual_trust.py](#test_contextual_trust), [test_contextual_trust_db.py](#test_contextual_trust_db), [test_untrust_contrasts.py](#test_untrust_contrasts), [test_untrust_replay.py](#test_untrust_replay).

<a id="cobertura-p07"></a>

**P07** — [test_entity_risk.py](#test_entity_risk), [test_entity_risk_db.py](#test_entity_risk_db), [test_temporal_live_db.py](#test_temporal_live_db).

<a id="cobertura-p08"></a>

**P08** — [test_financial_features.py](#test_financial_features).

<a id="cobertura-p09"></a>

**P09** — [test_gnn_contribution.py](#test_gnn_contribution), [test_gnn_false_positives.py](#test_gnn_false_positives), [test_gnn_http.py](#test_gnn_http), [test_temporal_case.py](#test_temporal_case), [test_temporal_gnn.py](#test_temporal_gnn), [test_temporal_live.py](#test_temporal_live), [test_temporal_live_db.py](#test_temporal_live_db).

<a id="cobertura-p10"></a>

**P10** — [test_api_security.py](#test_api_security), [test_gnn_http.py](#test_gnn_http), [test_metadata.py](#test_metadata), [test_pix.py](#test_pix), [test_temporal_live.py](#test_temporal_live).

<a id="cobertura-p11"></a>

**P11** — [test_account_untrust_db.py](#test_account_untrust_db), [test_duplicate_payment.py](#test_duplicate_payment), [test_entity_risk_db.py](#test_entity_risk_db), [test_gnn_contribution.py](#test_gnn_contribution), [test_history_audit.py](#test_history_audit), [test_no_history.py](#test_no_history), [test_pix.py](#test_pix), [test_temporal_case.py](#test_temporal_case), [test_temporal_live.py](#test_temporal_live), [test_untrust_replay.py](#test_untrust_replay).

<a id="cobertura-p12"></a>

**P12** — [test_gnn_contribution.py](#test_gnn_contribution), [test_gnn_http.py](#test_gnn_http), [test_history_audit.py](#test_history_audit), [test_metadata.py](#test_metadata).

<a id="cobertura-p13"></a>

**P13** — [test_api_security.py](#test_api_security).

<a id="cobertura-p14"></a>

**P14** — [test_gnn_false_positives.py](#test_gnn_false_positives), [test_gnn_validation.py](#test_gnn_validation), [test_graph_untrust_experiment.py](#test_graph_untrust_experiment), [test_temporal_case.py](#test_temporal_case), [test_temporal_gnn.py](#test_temporal_gnn).

## Funções atuais

Os nomes são os identificadores exatos do código. A coluna Casos vem do pytest;
uma função parametrizada pode produzir vários casos. As condições e asserções
completas ficam no link do código, evitando descrever resultados de funções
renomeadas ou de parametrizações removidas.

<a id="test_access_patterns"></a>

### Aparelhos, canal e horário

| Função | Casos |
|---|---:|
| [`test_night_rule_uses_app_and_brasilia_boundaries`](../tests/test_access_patterns.py#L38) | 8 |
| [`test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits`](../tests/test_access_patterns.py#L48) | 4 |
| [`test_configured_night_start_controls_the_signal`](../tests/test_access_patterns.py#L66) | 2 |
| [`test_invalid_access_policy`](../tests/test_access_patterns.py#L90) | 6 |
| [`test_shared_device_counts_distinct_owners_and_excludes_old_future_events`](../tests/test_access_patterns.py#L95) | 1 |
| [`test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate`](../tests/test_access_patterns.py#L115) | 1 |
| [`test_shared_device_concurrency_sees_prior_commits`](../tests/test_access_patterns.py#L127) | 1 |
| [`test_repository_recognizes_habitual_night_use`](../tests/test_access_patterns.py#L141) | 1 |
| [`test_repository_novel_app_night_combines_context_with_device`](../tests/test_access_patterns.py#L151) | 1 |

<a id="test_account_untrust"></a>

### Incremento e restrição própria

| Função | Casos |
|---|---:|
| [`test_increment_uses_current_rule_evidence_and_never_account_score`](../tests/test_account_untrust.py#L26) | 1 |
| [`test_account_thresholds_and_repeated_evidence_guard`](../tests/test_account_untrust.py#L51) | 9 |
| [`test_active_block_does_not_refresh_itself_even_on_velocity_risk`](../tests/test_account_untrust.py#L63) | 1 |
| [`test_first_transaction_and_account_age_alone_do_not_build_untrust`](../tests/test_account_untrust.py#L76) | 1 |
| [`test_single_low_risk_novelty_does_not_accumulate`](../tests/test_account_untrust.py#L89) | 1 |
| [`test_disabled_account_control_ignores_history_and_current_evidence`](../tests/test_account_untrust.py#L100) | 1 |
| [`test_notification_indicates_threshold_crossing_without_claiming_delivery`](../tests/test_account_untrust.py#L109) | 1 |
| [`test_invalid_untrust_policy_fails_startup`](../tests/test_account_untrust.py#L131) | 7 |
| [`test_risk_repetitions_escalate_normal_next_pix_without_changing_its_risk_score`](../tests/test_account_untrust.py#L136) | 1 |
| [`test_untrust_is_per_account_not_all_accounts_of_same_owner`](../tests/test_account_untrust.py#L150) | 1 |
| [`test_same_account_opening_date_does_not_reset_untrust_and_invalid_payload_does_not_add_points`](../tests/test_account_untrust.py#L163) | 1 |
| [`test_concurrent_account_attempts_cannot_lose_increments`](../tests/test_account_untrust.py#L176) | 1 |
| [`test_server_clock_not_caller_event_time_is_passed_to_account_history`](../tests/test_account_untrust.py#L185) | 1 |
| [`test_opt_in_block_requires_threshold_and_events_and_never_relaxes_prior_control`](../tests/test_account_untrust.py#L216) | 8 |

<a id="test_account_untrust_db"></a>

### Expiração e persistência do acumulado

| Função | Casos |
|---|---:|
| [`test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts`](../tests/test_account_untrust_db.py#L15) | 1 |

<a id="test_api_security"></a>

### Transporte, headers e erros

| Função | Casos |
|---|---:|
| [`test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length`](../tests/test_api_security.py#L66) | 3 |
| [`test_exact_size_limit_preserves_body_for_validation`](../tests/test_api_security.py#L79) | 1 |
| [`test_pix_requires_json_content_type`](../tests/test_api_security.py#L92) | 3 |
| [`test_malformed_content_length_is_rejected`](../tests/test_api_security.py#L100) | 4 |
| [`test_body_read_has_total_deadline`](../tests/test_api_security.py#L111) | 1 |
| [`test_request_without_internal_token_reaches_endpoint_and_sets_security_headers`](../tests/test_api_security.py#L121) | 2 |
| [`test_unhandled_error_does_not_leak_exception_details_and_is_correlated`](../tests/test_api_security.py#L137) | 1 |
| [`test_success_and_not_found_http_responses_prohibit_caching`](../tests/test_api_security.py#L154) | 1 |
| [`test_oversized_http_request_does_not_consume_transaction_id`](../tests/test_api_security.py#L165) | 1 |

<a id="test_contextual_trust"></a>

### Atenuação e atribuição própria

| Função | Casos |
|---|---:|
| [`test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence`](../tests/test_contextual_trust.py#L33) | 1 |
| [`test_insufficient_or_invalid_evidence_cannot_grant_attenuation`](../tests/test_contextual_trust.py#L57) | 5 |
| [`test_relationship_compatibility_boundaries_are_inclusive_and_exact`](../tests/test_contextual_trust.py#L68) | 4 |
| [`test_familiar_relationship_never_neutralizes_independent_controls`](../tests/test_contextual_trust.py#L82) | 4 |
| [`test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar`](../tests/test_contextual_trust.py#L91) | 1 |
| [`test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust`](../tests/test_contextual_trust.py#L99) | 1 |
| [`test_invalid_contextual_policy_fails_before_accepting_requests`](../tests/test_contextual_trust.py#L117) | 6 |
| [`test_destination_evidence_intervenes_without_accusing_the_sender`](../tests/test_contextual_trust.py#L122) | 1 |
| [`test_mixed_sender_and_destination_evidence_preserves_only_own_increment`](../tests/test_contextual_trust.py#L139) | 1 |
| [`test_hypothetical_critical_destination_detector_cannot_create_own_risk`](../tests/test_contextual_trust.py#L157) | 1 |

<a id="test_contextual_trust_db"></a>

### Amostras e relógios no banco

| Função | Casos |
|---|---:|
| [`test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals`](../tests/test_contextual_trust_db.py#L60) | 1 |
| [`test_backdated_requests_received_on_one_day_cannot_manufacture_trust`](../tests/test_contextual_trust_db.py#L88) | 1 |
| [`test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk`](../tests/test_contextual_trust_db.py#L99) | 1 |
| [`test_contextual_decision_is_persisted_and_retry_and_get_preserve_it`](../tests/test_contextual_trust_db.py#L128) | 1 |
| [`test_destination_attempts_remain_in_history_without_tainting_normal_next_payment`](../tests/test_contextual_trust_db.py#L162) | 1 |
| [`test_post_get_and_retry_preserve_contextual_response_without_duplicating_history`](../tests/test_contextual_trust_db.py#L201) | 1 |

<a id="test_duplicate_payment"></a>

### Possível duplicidade

| Função | Casos |
|---|---:|
| [`test_duplicate_window_and_future_exclusion`](../tests/test_duplicate_payment.py#L21) | 5 |
| [`test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed`](../tests/test_duplicate_payment.py#L37) | 1 |
| [`test_different_payment_identity_does_not_trigger_duplicate`](../tests/test_duplicate_payment.py#L50) | 5 |
| [`test_changed_device_and_opening_dates_do_not_hide_duplicate`](../tests/test_duplicate_payment.py#L67) | 1 |
| [`test_rejected_attempt_is_not_a_possible_previous_payment`](../tests/test_duplicate_payment.py#L78) | 1 |
| [`test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent`](../tests/test_duplicate_payment.py#L86) | 1 |
| [`test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust`](../tests/test_duplicate_payment.py#L98) | 1 |
| [`test_repository_respects_custom_duplicate_window`](../tests/test_duplicate_payment.py#L113) | 1 |
| [`test_duplicate_never_overrides_a_hard_rejection`](../tests/test_duplicate_payment.py#L137) | 1 |
| [`test_invalid_duplicate_window`](../tests/test_duplicate_payment.py#L148) | 5 |

<a id="test_dynamic_profile"></a>

### Perfil somente por aprovações

| Função | Casos |
|---|---:|
| [`test_reference_average_is_independent_of_available_sample_count`](../tests/test_dynamic_profile.py#L16) | 3 |
| [`test_fractional_average_is_compared_exactly_and_policy_is_configurable`](../tests/test_dynamic_profile.py#L29) | 1 |
| [`test_invalid_dynamic_profile_configuration`](../tests/test_dynamic_profile.py#L40) | 10 |
| [`test_repository_uses_last_ten_approved_pix_without_day_cutoff`](../tests/test_dynamic_profile.py#L45) | 1 |
| [`test_pending_two_factor_pix_cannot_bootstrap_amount_history`](../tests/test_dynamic_profile.py#L81) | 1 |
| [`test_rejected_and_pending_attempts_do_not_inflate_approved_profile`](../tests/test_dynamic_profile.py#L96) | 1 |
| [`test_old_pending_attempts_never_establish_value_or_familiarity`](../tests/test_dynamic_profile.py#L113) | 1 |

<a id="test_entity_risk"></a>

### Titular, vínculos e ocorrências

| Função | Casos |
|---|---:|
| [`test_clean_own_history_and_ten_controlled_fraudulent_companies_are_distinct`](../tests/test_entity_risk.py#L80) | 1 |
| [`test_new_company_inherits_exposure_through_verified_common_controller`](../tests/test_entity_risk.py#L97) | 1 |
| [`test_multiple_company_levels_and_cycles_do_not_duplicate_events`](../tests/test_entity_risk.py#L108) | 1 |
| [`test_same_incident_across_ten_cnpjs_is_one_independent_evidence`](../tests/test_entity_risk.py#L121) | 1 |
| [`test_company_branches_are_one_company_root_not_ten_companies`](../tests/test_entity_risk.py#L130) | 1 |
| [`test_weak_roles_do_not_become_controllers_or_trigger_multiple_incident_override`](../tests/test_entity_risk.py#L142) | 3 |
| [`test_unverified_future_ended_or_post_incident_membership_does_not_inherit_fraud`](../tests/test_entity_risk.py#L160) | 5 |
| [`test_incident_must_be_known_active_and_not_revoked_at_decision`](../tests/test_entity_risk.py#L174) | 3 |
| [`test_event_before_24_hours_remains_confirmed_until_explicit_expiry_or_revocation`](../tests/test_entity_risk.py#L179) | 1 |
| [`test_rule_untrust_aggregates_across_accounts_without_inheriting_relational_scores`](../tests/test_entity_risk.py#L189) | 1 |
| [`test_rule_evidence_expires_by_received_clock_and_future_evidence_is_excluded`](../tests/test_entity_risk.py#L204) | 1 |
| [`test_rule_evidence_from_before_ownership_does_not_create_soft_exposure`](../tests/test_entity_risk.py#L214) | 1 |
| [`test_clean_companies_do_not_dilute_high_risk_company`](../tests/test_entity_risk.py#L221) | 1 |
| [`test_truncated_history_is_unknown_not_clean_and_confirmed_registry_still_works`](../tests/test_entity_risk.py#L227) | 1 |
| [`test_oversized_corporate_graph_abstains_from_related_inference_but_preserves_direct_evidence`](../tests/test_entity_risk.py#L234) | 1 |
| [`test_shadow_preserves_scores_decision_and_account_evidence`](../tests/test_entity_risk.py#L245) | 1 |
| [`test_verified_entities_remain_one_capped_factor_and_preserve_own_evidence`](../tests/test_entity_risk.py#L256) | 1 |
| [`test_graph_zero_weight_disables_corporate_escalation_and_prior_rejection_is_preserved`](../tests/test_entity_risk.py#L268) | 1 |
| [`test_registry_rejects_masked_documents_duplicate_incidents_invalid_dates_and_untrusted_extra_fields`](../tests/test_entity_risk.py#L277) | 1 |
| [`test_registry_loading_is_strict_hashed_and_off_is_explicit`](../tests/test_entity_risk.py#L288) | 1 |

<a id="test_entity_risk_db"></a>

### Histórico real do titular

| Função | Casos |
|---|---:|
| [`test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score`](../tests/test_entity_risk_db.py#L55) | 1 |
| [`test_controller_new_account_preserves_own_titular_risk_and_saved_decision`](../tests/test_entity_risk_db.py#L77) | 1 |
| [`test_postgres_payment_query_includes_receipts_and_bounds_history`](../tests/test_entity_risk_db.py#L104) | 1 |
| [`test_confirmed_corporate_exposure_reaches_saved_controller_result`](../tests/test_entity_risk_db.py#L121) | 1 |

<a id="test_financial_features"></a>

### Recebimentos e repasses

| Função | Casos |
|---|---:|
| [`test_risky_receipt_is_separate_from_risky_destination_and_max_is_not_diluted`](../tests/test_financial_features.py#L20) | 1 |
| [`test_repass_pairs_are_distinct_and_pending_is_only_an_attempt_proxy`](../tests/test_financial_features.py#L34) | 1 |
| [`test_future_old_rejected_and_self_transfers_do_not_create_exposure`](../tests/test_financial_features.py#L49) | 1 |
| [`test_truncation_and_unknown_counterparty_risk_are_explicit`](../tests/test_financial_features.py#L61) | 1 |

<a id="test_gnn_contribution"></a>

### Contribuição ativa, manifesto e replay

| Função | Casos |
|---|---:|
| [`test_frozen_threshold_is_inclusive_and_never_adds_points`](../tests/test_gnn_contribution.py#L54) | 5 |
| [`test_observation_modes_do_not_intervene_even_with_maximum_score`](../tests/test_gnn_contribution.py#L69) | 2 |
| [`test_contribution_preserves_every_existing_restriction_and_its_cause`](../tests/test_gnn_contribution.py#L80) | 10 |
| [`test_abstention_cannot_generate_a_restriction`](../tests/test_gnn_contribution.py#L101) | 7 |
| [`test_policy_change_disables_graph_contribution_until_revalidated`](../tests/test_gnn_contribution.py#L111) | 3 |
| [`test_old_model_can_still_observe_but_cannot_use_new_models_cut`](../tests/test_gnn_contribution.py#L118) | 1 |
| [`test_missing_or_invalid_manifest_does_not_disable_rules_or_allow_ungated_contribution`](../tests/test_gnn_contribution.py#L126) | 4 |
| [`test_manifest_rejects_invalid_thresholds`](../tests/test_gnn_contribution.py#L138) | 7 |
| [`test_runtime_manifest_is_exactly_the_frozen_calibration_and_matches_full_baseline_policy`](../tests/test_gnn_contribution.py#L147) | 1 |
| [`test_runtime_combination_matches_frozen_experimental_proposal_on_new_histories`](../tests/test_gnn_contribution.py#L162) | 1 |
| [`test_live_contribution_uses_real_sql_without_self_reinforcement_and_preserves_replay`](../tests/test_gnn_contribution.py#L177) | 2 |
| [`test_http_combined_decision_has_graph_reason_and_immutable_replay`](../tests/test_gnn_contribution.py#L233) | 2 |

<a id="test_gnn_false_positives"></a>

### Negativos difíceis, calibração e artefatos

| Função | Casos |
|---|---:|
| [`test_conservative_cut_leaves_room_for_sampling_uncertainty`](../tests/test_gnn_false_positives.py#L34) | 1 |
| [`test_conservative_cut_cannot_hide_errors_in_a_small_legitimate_group`](../tests/test_gnn_false_positives.py#L46) | 1 |
| [`test_conservative_cut_disables_intervention_when_sample_is_too_small`](../tests/test_gnn_false_positives.py#L55) | 1 |
| [`test_false_positive_histories_are_valid_reproducible_and_strictly_before_candidate`](../tests/test_gnn_false_positives.py#L62) | 72 |
| [`test_identical_observations_do_not_prove_the_synthetic_source_intent`](../tests/test_gnn_false_positives.py#L77) | 1 |
| [`test_split_identities_and_transaction_ids_do_not_overlap`](../tests/test_gnn_false_positives.py#L84) | 1 |
| [`test_incoming_and_outgoing_bootcamp_flows_keep_one_account_identity`](../tests/test_gnn_false_positives.py#L105) | 1 |
| [`test_suppressing_every_alarm_cannot_pass_the_improvement_gate`](../tests/test_gnn_false_positives.py#L116) | 1 |
| [`test_legitimate_contexts_preserve_bounded_rule_scores_without_a_gnn`](../tests/test_gnn_false_positives.py#L144) | 5 |
| [`test_training_graph_matches_the_bounded_sql_inference_graph`](../tests/test_gnn_false_positives.py#L155) | 3 |
| [`test_parallel_scenarios_keep_their_own_simulated_clock_and_match_sequential_sql`](../tests/test_gnn_false_positives.py#L171) | 1 |
| [`test_frozen_experiment_keeps_separate_thresholds_artifacts_and_all_three_seeds`](../tests/test_gnn_false_positives.py#L190) | 1 |
| [`test_candidate_artifact_matches_frozen_hash_and_preserves_its_training_policy`](../tests/test_gnn_false_positives.py#L217) | 3 |
| [`test_default_shadow_model_separates_bootcamp_regressions_with_frozen_cut`](../tests/test_gnn_false_positives.py#L228) | 2 |
| [`test_model_rejects_invalid_training_policy_metadata`](../tests/test_gnn_false_positives.py#L241) | 5 |
| [`test_conservative_experiment_uses_fresh_splits_and_frozen_cuts_for_both_strategies`](../tests/test_gnn_false_positives.py#L250) | 1 |
| [`test_measured_models_cannot_separate_identical_histories_with_opposite_assumed_intents`](../tests/test_gnn_false_positives.py#L272) | 2 |

<a id="test_gnn_http"></a>

### Resumo HTTP do grafo

| Função | Casos |
|---|---:|
| [`test_shadow_v2_assessment_is_saved_and_replayed`](../tests/test_gnn_http.py#L9) | 1 |
| [`test_future_cross_payer_history_cannot_influence_graph`](../tests/test_gnn_http.py#L38) | 1 |

<a id="test_gnn_validation"></a>

### Propostas e critérios de avaliação

| Função | Casos |
|---|---:|
| [`test_candidate_never_relaxes_or_escalates_an_existing_intervention`](../tests/test_gnn_validation.py#L44) | 4 |
| [`test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs`](../tests/test_gnn_validation.py#L59) | 5 |
| [`test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score`](../tests/test_gnn_validation.py#L68) | 1 |
| [`test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases`](../tests/test_gnn_validation.py#L73) | 1 |
| [`test_calibration_without_both_classes_disables_proposals`](../tests/test_gnn_validation.py#L82) | 2 |
| [`test_report_separates_false_alarm_rate_from_incremental_legitimate_friction`](../tests/test_gnn_validation.py#L88) | 1 |
| [`test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget`](../tests/test_gnn_validation.py#L102) | 1 |
| [`test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account`](../tests/test_gnn_validation.py#L111) | 1 |
| [`test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow`](../tests/test_gnn_validation.py#L126) | 2 |
| [`test_validation_uses_real_sql_without_persisting_synthetic_scenarios`](../tests/test_gnn_validation.py#L174) | 2 |

<a id="test_graph_untrust_experiment"></a>

### Heurísticas de vizinhança offline

| Função | Casos |
|---|---:|
| [`test_two_hops_finds_independent_evidence_without_counting_paths_or_root`](../tests/test_graph_untrust_experiment.py#L64) | 1 |
| [`test_future_and_expired_evidence_do_not_increase_current_risk`](../tests/test_graph_untrust_experiment.py#L78) | 1 |
| [`test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy`](../tests/test_graph_untrust_experiment.py#L86) | 1 |
| [`test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages`](../tests/test_graph_untrust_experiment.py#L92) | 1 |
| [`test_neighbor_budget_keeps_latest_contacts_and_bounds_search`](../tests/test_graph_untrust_experiment.py#L100) | 1 |
| [`test_repass_requires_distinct_receipts_time_order_value_and_different_destination`](../tests/test_graph_untrust_experiment.py#L109) | 1 |
| [`test_replay_deduplicates_retries_and_excludes_future_and_candidate`](../tests/test_graph_untrust_experiment.py#L125) | 1 |
| [`test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate`](../tests/test_graph_untrust_experiment.py#L139) | 1 |
| [`test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint`](../tests/test_graph_untrust_experiment.py#L149) | 1 |
| [`test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly`](../tests/test_graph_untrust_experiment.py#L160) | 18 |

<a id="test_history_audit"></a>

### Elegibilidade e imutabilidade

| Função | Casos |
|---|---:|
| [`test_history_status_eligibility_is_explicit`](../tests/test_history_audit.py#L47) | 3 |
| [`test_familiarity_expires_but_amount_profile_has_no_day_cutoff`](../tests/test_history_audit.py#L77) | 3 |
| [`test_database_refuses_history_mutation`](../tests/test_history_audit.py#L96) | 2 |
| [`test_committed_payload_and_evidence_survive_new_connection`](../tests/test_history_audit.py#L112) | 3 |
| [`test_receiving_pix_does_not_establish_outgoing_payer_profile`](../tests/test_history_audit.py#L137) | 1 |
| [`test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls`](../tests/test_history_audit.py#L151) | 1 |

<a id="test_metadata"></a>

### Resumo público e auditoria interna

| Função | Casos |
|---|---:|
| [`test_minimal_http_response_details_and_saved_audit`](../tests/test_metadata.py#L21) | 1 |
| [`test_hard_limit_has_readable_rule_name`](../tests/test_metadata.py#L45) | 1 |
| [`test_approved_http_response_has_empty_rules_only_when_requested`](../tests/test_metadata.py#L58) | 1 |
| [`test_processing_timer_covers_analysis_and_is_not_recomputed`](../tests/test_metadata.py#L73) | 1 |
| [`test_legacy_summary_does_not_change_evidence`](../tests/test_metadata.py#L102) | 1 |
| [`test_factor_list_and_uncapped_sum_stay_internal`](../tests/test_metadata.py#L120) | 2 |
| [`test_all_current_rules_have_readable_aliases`](../tests/test_metadata.py#L141) | 1 |
| [`test_public_graph_score_is_present_only_when_available`](../tests/test_metadata.py#L160) | 9 |
| [`test_details_only_list_effective_rules_and_mandatory_controls`](../tests/test_metadata.py#L175) | 1 |
| [`test_rule_names_explain_accumulated_risk_overrides`](../tests/test_metadata.py#L206) | 2 |
| [`test_no_rules_returns_empty_details_instead_of_a_no_rule_alias`](../tests/test_metadata.py#L215) | 1 |

<a id="test_no_history"></a>

### Piso de R$ 500 e replay de política

| Função | Casos |
|---|---:|
| [`test_no_history_amount_floor`](../tests/test_no_history.py#L19) | 12 |
| [`test_no_history_amount_floor_is_configurable`](../tests/test_no_history.py#L38) | 2 |
| [`test_no_history_amount_floor_requires_positive_integer_cents`](../tests/test_no_history.py#L49) | 6 |
| [`test_low_value_without_history_still_respects_other_controls`](../tests/test_no_history.py#L62) | 3 |
| [`test_first_pix_http_boundary_and_replay`](../tests/test_no_history.py#L75) | 3 |
| [`test_pending_attempt_cannot_raise_the_reference_for_a_small_pix`](../tests/test_no_history.py#L85) | 1 |
| [`test_policy_change_does_not_recompute_a_saved_first_pix`](../tests/test_no_history.py#L101) | 1 |

<a id="test_pix"></a>

### Contrato, histórico e concorrência

| Função | Casos |
|---|---:|
| [`test_all_reasons_and_rejection_priority`](../tests/test_pix.py#L11) | 1 |
| [`test_sixth_attempt_is_rejected_and_rejections_are_saved`](../tests/test_pix.py#L23) | 1 |
| [`test_retries_do_not_inflate_velocity`](../tests/test_pix.py#L35) | 1 |
| [`test_changed_payload_conflicts_and_preserves_original`](../tests/test_pix.py#L42) | 1 |
| [`test_equivalent_timezone_and_document_format_replay`](../tests/test_pix.py#L53) | 1 |
| [`test_velocity_window_and_future_history`](../tests/test_pix.py#L65) | 3 |
| [`test_accumulated_value_boundary`](../tests/test_pix.py#L71) | 1 |
| [`test_new_destination_scores_only_above_minimum`](../tests/test_pix.py#L78) | 1 |
| [`test_missing_geolocation_is_valid`](../tests/test_pix.py#L91) | 1 |
| [`test_cnpj_is_valid`](../tests/test_pix.py#L96) | 1 |
| [`test_invalid_payload_is_rejected_without_consuming_id`](../tests/test_pix.py#L128) | 22 |
| [`test_required_and_unknown_fields`](../tests/test_pix.py#L141) | 1 |
| [`test_missing_transaction`](../tests/test_pix.py#L149) | 1 |
| [`test_business_endpoints_accept_requests_without_internal_token`](../tests/test_pix.py#L154) | 2 |
| [`test_public_health_and_openapi`](../tests/test_pix.py#L160) | 1 |
| [`test_concurrent_retries_share_one_analysis`](../tests/test_pix.py#L172) | 1 |
| [`test_concurrent_distinct_pix_cannot_bypass_velocity`](../tests/test_pix.py#L179) | 1 |
| [`test_same_id_different_payers_cannot_overwrite`](../tests/test_pix.py#L188) | 1 |
| [`test_velocity_is_shared_by_payer_across_accounts`](../tests/test_pix.py#L196) | 1 |

<a id="test_risk_factors"></a>

### Pesos, fatores e configuração

| Função | Casos |
|---|---:|
| [`test_fractional_factor_weight_is_truncated_before_decision_and_explained`](../tests/test_risk_factors.py#L20) | 1 |
| [`test_increasing_factor_weights_can_block_a_transaction`](../tests/test_risk_factors.py#L41) | 1 |
| [`test_rule_remapping_changes_factor_cap_and_rejection_guard`](../tests/test_risk_factors.py#L55) | 1 |
| [`test_related_rules_share_one_factor_and_reconstruct_capped_score`](../tests/test_risk_factors.py#L96) | 2 |
| [`test_invalid_factor_weight`](../tests/test_risk_factors.py#L115) | 5 |
| [`test_every_rule_references_a_valid_factor`](../tests/test_risk_factors.py#L120) | 1 |
| [`test_load_partial_policy_and_default_configuration`](../tests/test_risk_factors.py#L127) | 1 |
| [`test_invalid_file_cannot_be_activated`](../tests/test_risk_factors.py#L148) | 7 |

<a id="test_risk_score"></a>

### Resultados integrados das regras

| Função | Casos |
|---|---:|
| [`test_first_pix_requests_two_factor_and_saves_explanation`](../tests/test_risk_score.py#L45) | 1 |
| [`test_approved_history_makes_device_and_young_destination_familiar`](../tests/test_risk_score.py#L58) | 1 |
| [`test_weak_device_signal_alone_approves`](../tests/test_risk_score.py#L73) | 1 |
| [`test_two_weak_groups_combine_into_two_factor`](../tests/test_risk_score.py#L84) | 1 |
| [`test_related_counterparty_signals_are_capped`](../tests/test_risk_score.py#L94) | 1 |
| [`test_high_profile_signal_alone_requires_two_factor`](../tests/test_risk_score.py#L105) | 1 |
| [`test_high_profile_plus_new_account_rejects`](../tests/test_risk_score.py#L115) | 1 |
| [`test_factor_sum_can_exceed_final_score_cap`](../tests/test_risk_score.py#L126) | 1 |
| [`test_activity_group_cap_preserves_all_hard_reasons`](../tests/test_risk_score.py#L140) | 1 |

<a id="test_rule_audit"></a>

### Fronteiras das 13 regras

| Função | Casos |
|---|---:|
| [`test_each_rule_activation_boundary_and_exclusions`](../tests/test_rule_audit.py#L229) | 46 |
| [`test_every_configured_rule_has_positive_and_negative_audit_cases`](../tests/test_rule_audit.py#L247) | 1 |

<a id="test_scoring_policy"></a>

### Prioridade, limiares e limites fortes

| Função | Casos |
|---|---:|
| [`test_score_boundaries_and_rejection_factor_guard`](../tests/test_scoring_policy.py#L26) | 8 |
| [`test_decision_uses_configured_thresholds`](../tests/test_scoring_policy.py#L50) | 4 |
| [`test_configured_rejection_requires_three_positive_factors`](../tests/test_scoring_policy.py#L76) | 2 |
| [`test_missing_reference_priority_survives_zero_weights`](../tests/test_scoring_policy.py#L128) | 4 |
| [`test_invalid_policy_cannot_be_activated`](../tests/test_scoring_policy.py#L164) | 9 |

<a id="test_temporal_case"></a>

### Caso temporal completo e SQL

| Função | Casos |
|---|---:|
| [`test_export_contains_actual_nodes_edges_and_all_rule_results`](../tests/test_temporal_case.py#L21) | 1 |
| [`test_v2_case_runs_through_database_decision_and_replay`](../tests/test_temporal_case.py#L41) | 1 |

<a id="test_temporal_gnn"></a>

### Schema, atributos, pesos e paridade

| Função | Casos |
|---|---:|
| [`test_payment_and_device_relations_are_separate_and_directional`](../tests/test_temporal_gnn.py#L63) | 1 |
| [`test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect`](../tests/test_temporal_gnn.py#L76) | 1 |
| [`test_holder_identity_deduplicates_accounts_on_a_shared_device`](../tests/test_temporal_gnn.py#L88) | 1 |
| [`test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window`](../tests/test_temporal_gnn.py#L102) | 4 |
| [`test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass`](../tests/test_temporal_gnn.py#L109) | 1 |
| [`test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact`](../tests/test_temporal_gnn.py#L126) | 1 |
| [`test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak`](../tests/test_temporal_gnn.py#L134) | 1 |
| [`test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge`](../tests/test_temporal_gnn.py#L153) | 1 |
| [`test_truncated_conflicting_and_unbounded_history_are_refused`](../tests/test_temporal_gnn.py#L162) | 1 |
| [`test_fast_and_slow_pair_changes_temporal_features_and_v2_prediction`](../tests/test_temporal_gnn.py#L175) | 1 |
| [`test_synthetic_split_dates_and_openings_are_valid`](../tests/test_temporal_gnn.py#L185) | 3 |
| [`test_exported_v2_is_safe_finite_and_permutation_invariant`](../tests/test_temporal_gnn.py#L195) | 3 |
| [`test_comparison_selects_on_validation_and_records_parity_for_every_seed`](../tests/test_temporal_gnn.py#L207) | 1 |
| [`test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics`](../tests/test_temporal_gnn.py#L228) | 4 |
| [`test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget`](../tests/test_temporal_gnn.py#L245) | 3 |
| [`test_threshold_does_not_split_tied_legitimate_and_fraud_scores`](../tests/test_temporal_gnn.py#L251) | 1 |
| [`test_entity_identities_do_not_overlap_across_training_validation_and_test`](../tests/test_temporal_gnn.py#L257) | 1 |

<a id="test_temporal_live"></a>

### Inferência, abstenção e modos

| Função | Casos |
|---|---:|
| [`test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history`](../tests/test_temporal_live.py#L37) | 1 |
| [`test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis`](../tests/test_temporal_live.py#L50) | 1 |
| [`test_missing_v2_model_has_explicit_zero_contribution`](../tests/test_temporal_live.py#L68) | 2 |
| [`test_unvalidated_v2_contribution_cannot_be_enabled_accidentally`](../tests/test_temporal_live.py#L78) | 2 |
| [`test_incomplete_neighborhood_abstains_without_calling_model`](../tests/test_temporal_live.py#L86) | 4 |
| [`test_invalid_prediction_does_not_escape_as_a_fraud_score`](../tests/test_temporal_live.py#L98) | 4 |
| [`test_high_v2_prediction_remains_observational`](../tests/test_temporal_live.py#L107) | 1 |
| [`test_http_v2_runs_by_default_and_saved_evidence_is_replayed`](../tests/test_temporal_live.py#L116) | 1 |
| [`test_bad_model_json_is_unavailable_without_breaking_startup`](../tests/test_temporal_live.py#L134) | 4 |
| [`test_maximum_v2_prediction_preserves_zero_weight_mandatory_decisions`](../tests/test_temporal_live.py#L163) | 6 |
| [`test_disabled_or_unavailable_model_does_not_query_optional_history`](../tests/test_temporal_live.py#L190) | 2 |
| [`test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis`](../tests/test_temporal_live.py#L197) | 1 |
| [`test_model_prediction_failure_cannot_modify_or_break_rule_decision`](../tests/test_temporal_live.py#L205) | 1 |

<a id="test_temporal_live_db"></a>

### Vizinhança e relógios reais

| Função | Casos |
|---|---:|
| [`test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood`](../tests/test_temporal_live_db.py#L61) | 1 |
| [`test_own_history_uses_received_window_and_rejects_legacy_evidence`](../tests/test_temporal_live_db.py#L98) | 1 |
| [`test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample`](../tests/test_temporal_live_db.py#L129) | 3 |
| [`test_legacy_payload_cannot_break_optional_v2_observation`](../tests/test_temporal_live_db.py#L161) | 1 |
| [`test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay`](../tests/test_temporal_live_db.py#L185) | 4 |

<a id="test_untrust_contrasts"></a>

### Invariâncias e causas de intervenção

| Função | Casos |
|---|---:|
| [`test_same_request_different_context_has_a_specific_cause`](../tests/test_untrust_contrasts.py#L70) | 4 |
| [`test_identical_clean_pix_changes_only_because_of_accumulated_evidence`](../tests/test_untrust_contrasts.py#L85) | 1 |
| [`test_correlated_device_signals_accumulate_only_the_capped_contribution`](../tests/test_untrust_contrasts.py#L96) | 1 |
| [`test_reclassifying_a_noneligible_rule_does_not_create_suspicion`](../tests/test_untrust_contrasts.py#L109) | 3 |
| [`test_reclassifying_real_profile_evidence_does_not_erase_suspicion`](../tests/test_untrust_contrasts.py#L129) | 1 |
| [`test_temporal_observation_and_restriction_do_not_feed_own_increment`](../tests/test_untrust_contrasts.py#L147) | 2 |
| [`test_irrelevant_request_changes_preserve_decision_and_suspicion`](../tests/test_untrust_contrasts.py#L163) | 4 |

<a id="test_untrust_replay"></a>

### Equivalência offline/PostgreSQL

| Função | Casos |
|---|---:|
| [`test_replay_agrees_with_persisted_decisions_at_each_step`](../tests/test_untrust_replay.py#L88) | 13 |
| [`test_replay_rejects_conflicting_ids_instead_of_recounting_risk`](../tests/test_untrust_replay.py#L128) | 1 |
| [`test_comparison_report_attributes_the_same_pix_change_to_its_account_history`](../tests/test_untrust_replay.py#L136) | 2 |
