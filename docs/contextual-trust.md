# Perfil por relação e atribuição do risco

A política `pix-score-v9` contextualiza a anomalia de valor e distingue risco da operação
de evidência própria do pagador. Os parâmetros são hipóteses do projeto.

## Cofre de Confiança Contextual

A referência geral usa a média das últimas dez aprovações. Pendências
de 2FA não fornecem referência provisória; sem aprovações, o perfil fica indisponível.
O Cofre usa uma
amostra separada: somente aprovações locais sem limites críticos registrados,
com evento nos últimos `profile_days` (30) e recebidas antes da decisão.
Pendências de 2FA, rejeições e eventos futuros não compõem essa amostra.

| Parâmetro em `contextual_trust` | Padrão | Motivo |
|---|---:|---|
| `enabled` | true | Permite comparar a política com a contextualização desligada |
| `history_size` | 20 | Limita separadamente a amostra geral e a da relação |
| `minimum_payer_samples` | 5 | Evita inferir familiaridade com histórico geral escasso |
| `minimum_relationship_samples` | 3 | Exige repetição com a mesma conta de destino |
| `minimum_received_days` | 2 | Uma rajada de pedidos retroativos não fabrica dias de experiência |
| `minimum_ratio_percent` | 50 | Limite inferior de compatibilidade com a mediana da relação |
| `maximum_ratio_percent` | 200 | Limite superior de compatibilidade com a mediana da relação |

O pagador é o documento normalizado, como nas regras atuais. O destino inclui
instituição, agência, conta e documento, sem data de abertura. A origem não traz
instituição obrigatória; sua identidade local não comprova unicidade bancária global.
Os dias distintos são calculados por `created_at`, em UTC−3. Cada consulta ordena
por recebimento e ID interno e limita a quantidade de observações. A mediana usa
inteiros: `*_median_twice_cents` representa duas vezes o valor, preservando meias
unidades de centavo sem arredondamento monetário.

Com amostra suficiente e valor entre 0,5 e 2 vezes a mediana da relação, os pontos
ponderados de `amount_above_customer_profile` passam a zero. O sinal original,
seus pontos anteriores e a justificativa continuam nas evidências. Só esse sinal
é atenuado. Frequência, montante, dispositivo, conta, horário e grafo permanecem
independentes. As medianas não substituem a média geral da política atual.

A auditoria interna informa `applied`, `reason`, `profile_points_before`,
`profile_points_after`, amostras, medianas e versão. Esses dados não integram
o resumo HTTP; `include_details=true` acrescenta somente nomes de regras.
Isso é familiaridade local provisória; não é saldo, whitelist nem confirmação
de pagamento. Muitas aprovações próprias ainda podem sofrer manipulação; o
Cofre não concede imunidade nem comprova redução de fraude real.

## Origem dos sinais e decisão

Cada regra registra `subject` e `source`, além de observação, limiar e contribuição.
Os sujeitos são `sender`, `destination`, `relationship` e `transaction`.
O grupo configurável de pontuação não muda o sujeito da evidência.

`decision_causes` registra as evidências da intervenção selecionada. Para limite
forte, guarda os limites acionados; para score, guarda as contribuições positivas;
para exigência inicial, identifica a insuficiência de histórico; para acumulado
e vínculos, identifica a origem adicional. Não pretende encontrar um subconjunto
causal mínimo ou atribuir intenção criminosa. Aprovações têm lista vazia.

Sinais de conta destinatária recente e destinatário desconhecido continuam
influenciando a operação. Eles não produzem incremento de suspeita própria da origem.
Frequência, montante, desvio de perfil não atenuado e dispositivos continuam
elegíveis ao acumulado conforme suas regras. Todas as tentativas válidas continuam
gravadas e contando para frequência e montante, inclusive rejeições.

## Compatibilidade e implantação

As evidências próprias usam `account_untrust.evidence_version=sender-evidence-v2`.
As consultas de acumulado, titular e grafo temporal ignoram incrementos sem essa
versão: eles podem conter contribuições de destinatários da política antiga.
Os registros anteriores continuam consultáveis pelo GET e não são reescritos.
A versão de evidência impede transportar atribuições incompatíveis para a política atual.

A confiança contextual não exige colunas ou rotas próprias. Reinicie a API com a política e o código atualizados;
as migrações exigidas pela integração do grafo são documentadas separadamente.
O grafo v2 em `shadow` não modifica a ação. Em `contribute`, pode exigir 2FA
sem pontos nem realimentação, conforme o [manifesto ativo](gnn-contribution.md).

## Verificação

`tests/test_contextual_trust.py` compara relação conhecida/desconhecida, amostras
insuficientes, limites inclusivos, microtransações, configuração, ausência de
referência e controles independentes. `tests/test_contextual_trust_db.py` verifica
elegibilidade SQL, tempo de recebimento, isolamento do legado, tentativas de
destinatário sem contaminação e persistência da decisão em GET/retry.

`scripts/evaluate_untrust.py` reproduz a mesma contextualização, usando o horário
de evento como recebimento simulado. Os testes diferenciais com PostgreSQL
verificam essa equivalência sob um relógio de recebimento controlado.
