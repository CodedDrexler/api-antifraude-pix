# Política de risco e evidências

Política `pix-score-v9`. Fontes consultadas em 17/10/2026.
Os pontos são parâmetros demonstrativos do projeto, sem calibração em fraude real.

## Decisão

Todas as regras são avaliadas. Cada regra recebe seus pontos de `weights`,
multiplicados por `factor_weights / 100`, descartando a fração. O teto de cada
fator (`group_caps`) limita sua contribuição; a soma final fica entre 0 e 100.
Dentro do fator, a maior pontuação consome o teto primeiro; o código desempata.
Os fatores reduzem sobreposição óbvia, sem demonstrar independência estatística.

| Condição, em ordem de prioridade | Resultado |
|---|---|
| Limite forte de frequência ou montante | `rejected`, origem `hard_limit` |
| Score ≥ 80 com ao menos dois fatores positivos | `rejected`, origem `risk_score` |
| Referência de valores aprovada ausente e valor ≥ `no_history_min_amount` (R$ 500) | `two_factor_required`, mesmo com peso zero |
| Score ≥ 30 | `two_factor_required` |
| Restante | `approved` |

`risk_level` expressa apenas a faixa: `low` (<30), `elevated` (30–79), `high` (≥80).
Um fator alto sozinho exige 2FA. O serviço informa a ação ao integrador;
não executa autenticação nem liquidação.

## Regras padrão

| Código | Condição | Pontos / fator |
|---|---|---|
| `first_transaction` | Nenhuma tentativa anterior, sem perfil aprovado e valor ≥ `no_history_min_amount` | 30 / exposure |
| `insufficient_amount_history` | Há tentativas, mas nenhuma referência aprovada e valor ≥ `no_history_min_amount` | 30 / exposure |
| `possible_duplicate_payment` | Mesma conta de origem, destinatário e valor em até 120 s, com outro ID | 30 / duplication |
| `velocity_above_limit` | Cinco tentativas anteriores em 10 min | 80 / activity; forte |
| `accumulated_amount_above_limit` | Soma das tentativas em 10 min + atual ≥ R$ 30 mil | 80 / activity; forte |
| `new_source_account` | Conta de origem com menos de 7 dias | 15 / account |
| `new_destination_account` | Destino sem aprovação, conta <7 dias e valor ≥ R$ 500 | 15 / counterparty |
| `unfamiliar_destination` | Destino sem aprovação, três aprovações do pagador e valor ≥ R$ 500 | 15 / counterparty |
| `amount_above_customer_profile` | Valor ≥ média de referência × 5 | 80 / profile |
| `unfamiliar_device` | Aparelho sem aprovação, três aprovações do pagador e valor ≥ R$ 500 | 20 / device |
| `shared_device` | Aparelho ligado a pelo menos três titulares em 24 h, contando o atual | 30 / device |
| `multiple_devices` | Pelo menos três aparelhos do pagador em 24 h, contando o atual, e aparelho desconhecido | 20 / device |
| `unusual_night_app` | App à noite, fora do hábito, com novidade e exposição | 15 / access_context |

| Código estável | Nome exibido (`label`) | Teto |
|---|---|---|
| exposure | Histórico insuficiente para avaliar o Pix | 80 |
| activity | Quantidade e valor acumulado de Pix recentes | 80 |
| duplication | Possível repetição do mesmo pagamento | 30 |
| account | Tempo desde a abertura da conta de origem | 15 |
| counterparty | Conta de destino recente ou destinatário desconhecido | 25 |
| profile | Valor do Pix comparado aos pagamentos anteriores | 80 |
| device | Aparelho desconhecido, compartilhado ou trocado com frequência | 40 |
| access_context | Uso do aplicativo à noite fora do hábito do pagador | 15 |
| graph | Risco associado a vínculos societários verificados, se habilitados para contribuir | 20 |

Os códigos existentes foram preservados para integrações; os nomes legíveis
explicam os fatores ao usuário. Na API atual, `graph` recebe somente a contribuição
optativa de vínculos verificados em `entity_risk`. O único modelo de grafo é o v2,
que observa em `metadata.gnn_v2` e não adiciona pontos. Evidências antigas mantêm
seus códigos originais para consulta, sem reativar a implementação anterior.

Na v8, o [Cofre de Confiança Contextual](contextual-trust.md) pode zerar somente
os pontos da anomalia de perfil quando o valor é habitual na relação e há amostra
suficiente em dias distintos de recebimento. A regra original permanece na auditoria.
`subject` separa origem, destinatário, relação e transação; `decision_causes`
registra as evidências da intervenção. Destinatário não alimenta o acumulado próprio.

## O que cada histórico representa

As consultas por pagador usam o documento normalizado e o tempo do evento,
limitadas também aos registros disponíveis no instante de recebimento da análise.
Eventos futuros ficam fora; timestamps iguais incluem tentativas recebidas antes.
Repetir um ID não acrescenta observações. Eventos atrasados não alteram decisões salvas.

- **Possível duplicidade:** mesma identidade de conta de origem e de destino,
  mesmo valor em centavos e ID diferente, na janela inclusiva `[evento − 120 s, evento]`.
  A janela é configurável por `duplicate_window_seconds`, um inteiro positivo.
  Apenas análises `approved` ou `two_factor_required` são elegíveis; não comprovam
  pagamento ou liquidação. A tentativa mais recente é informada em `duplicate_payment`,
  inclusive na resposta resumida. Trocar aparelho ou data de abertura não altera
  a identidade da conta. As travas por pagador serializam tentativas simultâneas.
  Registros antigos sem `source_account_identity` não entram nessa comparação.
  O fator próprio tem teto de 30 e peso configurável; isoladamente pede 2FA no padrão.
  Não é limite forte e não integra os fatores elegíveis de `account_untrust`.

- **Frequência e montante:** todas as tentativas válidas nos últimos 10 minutos,
  inclusive rejeições e pendências. O valor atual entra no montante.
- **Perfil de valores:** até X aprovações anteriores (X=10), da mais recente para
  a mais antiga, com desempate pelo ID interno. Não há corte por dias.
- **Sem referência:** pendências de 2FA e rejeições nunca formam o perfil, mesmo
  quando não há aprovações. A partir de `no_history_min_amount` (50000 centavos),
  essa ausência exige 2FA; abaixo do limite, as demais regras decidem normalmente.
  O parâmetro aceita somente inteiro positivo. O padrão de R$ 500 é demonstrativo.
- **Familiaridade:** somente aprovações nos últimos 30 dias estabelecem confiança
  em aparelho e destino. Idade da conta é informada pelo integrador.
- **Diversidade de dispositivos:** todas as tentativas em 24 h, de qualquer
  decisão, mais o vínculo atual. Conta titulares e aparelhos distintos;
  repetições e várias contas do mesmo titular não multiplicam pessoas.
- **Hábito noturno:** aprovações do pagador em 30 dias, em qualquer canal, às
  quais o motor aplica a mesma faixa horária da análise atual.

A referência de valores compara inteiros: `amount × count >= sum × multiplier`.
Não há piso de valor ou amostra mínima para esse sinal. Com uma amostra, a
incerteza é maior; esse fator sozinho exige 2FA. Sem referência, exige 2FA somente
a partir do limite configurado, inclusive no primeiro Pix e com pesos zerados.
Nos detalhes: `registered_transactions`, `profile_transactions`, `profile_amount`,
`profile_average`, `profile_limit` e `profile_basis` (`approved`,
`unavailable`). As médias exibidas não decidem o resultado. Análises históricas
podem conservar a antiga referência `initial_pending_attempt`; GET/replay não a recalculam.

Usar aprovações evita que uma sequência de rejeições eleve o teto. Aprovação local
ainda não significa transação legítima ou liquidada; feedback confirmado permitiria
uma referência melhor. Média é sensível a extremos e escaladas aprovadas:
mediana/quantis, decaimento e limites por segmento precisam de avaliação com dados
reais antes de substituir a regra simples e reproduzível.

Compartilhamento pode ser legítimo (famílias, empresas). Por isso os sinais de
aparelho compartilham teto de 40, não são limites fortes e não rejeitam isoladamente.
A trava por aparelho serializa pagadores diferentes usando o mesmo device_id;
a trava por pagador protege uso simultâneo de aparelhos diferentes.
Os detalhes guardam contagens e janela, sem expor documentos de outros titulares.

## App, computador e período noturno

`unusual_night_app` exige todas as condições:

1. `source.channel` igual a `app`, ignorando maiúsculas e espaços nas bordas.
2. Horário de Brasília, UTC−3, de 20h inclusive a 6h exclusive.
3. Valor ≥ R$ 500 e três aprovações anteriores em 30 dias.
4. Nenhuma aprovação nessa faixa horária e aparelho ou destino desconhecido.

`night_start_hour` e `night_end_hour` ajustam a faixa do sinal heurístico;
não alteram os limites bancários. `internet_banking` e demais canais não recebem
esses pontos; os demais controles continuam. O canal vem de um integrador interno
confiável e não é inferido pelo device_id, IP ou geolocalização.

A [IN BCB 512, art. 3º](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=512&tipo=Instru%C3%A7%C3%A3o+Normativa+BCB)
prevê limites por período para pagadores PF; em geral, a noite vai de 20h a 6h,
com possibilidade de início às 22h. Para recebedor PF, o padrão noturno é R$ 1.000,
ressalvadas as solicitações e condições regulamentares. Não há isenção geral
por usar PC. Esse limite é por período e não deve ser confundido com o score.

A API não conhece os limites efetivos da conta, pedidos de alteração, cadastro de
beneficiários nem liquidações. Portanto não implementa o controle regulatório
com base em canal ou novidade local. `access_context.regulatory_limits_checked`
é `false`: o integrador precisa consultar e aplicar a gestão bancária correspondente.
A [orientação do BCB sobre novos dispositivos](https://bcb.gov.br/detalhenoticia/20390/noticia)
também cita celular e computador; desconhecido no nosso histórico não significa
não cadastrado no banco.

## Resposta, configuração e auditoria

O resumo público inclui `risk_score` e `bank_notification_required`, além de `key`
e `status`. `untrust_score` aparece somente quando há avaliação disponível do grafo;
o campo é omitido nos demais casos. O grafo não altera a decisão em `shadow`.
No padrão `contribute` do protótipo, pode elevar aprovação para 2FA com score
≥75,0977 e artefatos vinculados, sem acrescentar pontos ou rejeitar sozinho.
Veja os [limites da contribuição](gnn-contribution.md).

`include_details=true` acrescenta apenas `rules`, uma lista de strings com os
nomes legíveis das regras aplicadas. Os aliases estão em
[`rule_aliases.py`](../src/dtos/rule_aliases.py). Regras com contribuição zero
não aparecem, salvo limites fortes ou controles obrigatórios usados na decisão.
A lista também explica intervenções por acumulado da conta ou do titular.

A evidência completa continua salva: observações, limiares, pontos originais e
ponderados, contribuição efetiva, tetos, referências, contexto e política.
`group` continua equivalente a `risk_factor`. Internamente,
`risk_score = min(100, risk_factors_sum)`; somar as contribuições e subtrair
`score_cap_reduction` reconstrói o score. Esses campos não são expostos por HTTP.

O tempo mede o controller até antes da gravação, incluindo travas, consultas,
regras e grafo; exclui persistência, commit e HTTP. A duração fica apenas na
auditoria e não é inventada para registros antigos. GET e repetições usam a decisão salva.

O operador edita `config/risk-policy.json`; o cliente da transação não escolhe
pesos. Pesos percentuais vão de 0 a 200, pontos por regra de 0 a 100.
Pesos zero preservam os limites fortes e a exigência inicial de 2FA.
Configuração parcial mantém padrões; campos desconhecidos ou valores inválidos
impedem a inicialização. Altere a versão ao publicar mudanças.

`pix-score-v4` modificou a referência de valores, adicionou sinais de acesso e
ampliou o teto de dispositivos para 40. Análises anteriores conservam seu conteúdo;
use IDs novos para comparar políticas. Não há migração de decisões ou descarte de dados.

A v5 acrescenta
`account_untrust`, um controle separado de histórico por conta, com janela no
horário do servidor, 2FA a partir de 40 e indicação de aviso a partir de 60.
Não é somado ao `risk_score`. O bloqueio pelo acumulado fica desativado no padrão,
conforme a comparação sintética de efeitos adversos. Consulte a
[política de desconfiança por conta](account-untrust.md) para cálculo e avaliação.

A v6 acrescenta a detecção de possível Pix duplicado. Decisões já salvas mantêm
seu resultado e sua versão, inclusive nos reenvios do mesmo ID.

## Pesquisa e validação

A [documentação de score do Stripe Radar](https://docs.stripe.com/radar/transaction-risk-prevention)
e as [regras do Adyen Protect](https://docs.adyen.com/risk-management/configure-your-risk-profile/)
orientaram a separação entre sinais, score e ação; os pontos deste projeto não
reproduzem seus modelos. O [backtesting do Adyen](https://docs.adyen.com/risk-management/configure-your-risk-profile/custom-rules/#backtest-a-rule)
é uma referência para avaliar políticas futuras com resultados conhecidos.

Os testes cobrem faixas 29/30 e 79/80, tetos, proteção contra inflação da referência,
primeiro Pix, canais, fronteiras e fusos do horário, diversidade, histórico futuro,
idempotência e concorrência. Os cenários sintéticos não medem eficácia em fraude real.
Calibração exigiria rótulos de fraude, autenticação e liquidação; avaliação temporal;
taxas de falso positivo, fraude aprovada, perda e pedidos de 2FA; comparação com
baselines e monitoramento. [O grafo v2 tem documentação própria](graph-v2-api.md).
