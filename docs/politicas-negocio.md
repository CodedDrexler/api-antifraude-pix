# Entregável 2 — políticas de negócio consolidadas

Política **pix-score-v9**, conforme [configuração](../config/risk-policy.json) e
código revisados em **18/10/2026**. Os valores abaixo são os padrões do repositório;
o ambiente pode alterar os modos opcionais. "Negociação" corresponde às condições
de aprovação, 2FA, rejeição e atenuação configuradas pelo operador; não há negociação
dinâmica de limites com o cliente. Os códigos R01–R13 e P01–P14 preservam os vínculos
com a [análise individual dos testes](testes-politicas.md).

## 1. Conta enviadora, receptora e identidade

O objeto avaliado é **um Pix da origem para o destino**. A API não aprova a conta
receptora separadamente nem cria, nesse pedido, um novo incremento próprio para ela.

| Nível | Identificação e tratamento |
|---|---|
| Conta | Instituição/participante, agência, número e documento do titular. Data de abertura e aparelho não integram a identidade; mudar esses dados não reinicia o acumulado da mesma conta. Participante da origem é opcional: omitir/preencher esse campo muda a identidade de conta considerada. |
| Titular | CPF/CNPJ normalizado. Frequência, perfil, familiaridade e diversidade agregam contas do mesmo documento. O acumulado de cada conta continua separado. |
| Relação financeira | Pagador → conta destinatária, com direção, valores e tempo. Familiaridade e confiança contextual são específicas dessa direção; A→B não concede automaticamente familiaridade a B→A. |
| Relação societária | Vínculo de controle/participação fornecido e verificado pelo operador. Uma transferência não comprova sociedade. |

Sinais do destino podem restringir o Pix, mas não viram suspeita própria do
remetente. Receber um Pix não forma perfil de envio. Rejeição ou pendência são
tentativas registradas, sem comprovar liquidação ou sucesso de autenticação.
Fontes: [controlador](../src/controllers/pix_controller.py),
[histórico](../src/repositories/pix_repository.py), [atribuição](../src/risk/attribution.py).

<a id="p03"></a>

**P03 — Qual histórico vale para cada decisão**

| Uso | Base e janela |
|---|---|
| Frequência e montante | Todas as tentativas válidas de envio do pagador em 10 min, incluindo rejeições e pendências; o valor atual entra no montante. |
| Perfil de valores | Últimas até dez aprovações de envio do documento, sem corte por dias; uma aprovação já forma referência. |
| Aparelho/destino conhecidos e hábito noturno | Aprovações do pagador nos últimos 30 dias. "Conhecido" significa aprovação local, não cadastro bancário verificado. |
| Diversidade de aparelhos | Tentativas em 24h, contando titulares/aparelhos distintos e o vínculo atual. |
| Confiança contextual | Até 20 aprovações por conjunto, em 30 dias, sem limite forte registrado. |
| Suspeita própria da conta/titular | Incrementos independentes `sender-evidence-v2` recebidos em `(agora−24h, agora]`. |

Histórico financeiro exclui eventos posteriores ao Pix e informação ainda não
recebida na análise. Suspeita própria usa o relógio do servidor: retroagir a data
do Pix não apaga evidência vigente. Reenvios não acrescentam observações; decisões
antigas não são recalculadas. Legado permanece auditável sem inventar identidade
de conta ou reutilizar evidência de semântica incompatível.
[Testes P03](testes-politicas.md#cobertura-p03).

## 2. CPF, CNPJ e vínculos societários

CPF tem 11 dígitos; CNPJ, 14. O pedido aceita pontuação e normaliza para dígitos;
valida formato/tamanho, sem consultar cadastro ou verificar dígitos verificadores.
As mesmas 13 regras e limiares se aplicam a CPF→CPF, CPF→CNPJ, CNPJ→CPF e CNPJ→CNPJ.
Não há peso especial só por ser pessoa física ou jurídica.

<a id="p07"></a>

**P07 — Titular e exposição societária (`entity_risk`)**

- Mesmo documento agrega evidências próprias entre suas contas; CPF e CNPJ são
  identidades distintas. O histórico próprio do CPF não é fundido ao do CNPJ.
- Relações CPF→CNPJ e CNPJ→CNPJ exigem cadastro do operador com documento completo,
  papel, verificação, referência, início/fim e data de conhecimento. Não há integração
  automática com Receita/QSA nem associação por nome ou CPF mascarado.
- Papéis: controlador/beneficiário final **1**; administrador **0,5**; minoritário
  **0,2**; contador **0**. Papéis fracos não servem de ponte entre empresas.
- Busca até **três arestas societárias e 100 entidades**. Vínculos precisam estar
  ativos e conhecidos; a associação à empresa da ocorrência respeita também sua
  validade na época do incidente. Empresa nova pode ter exposição pelo controlador
  atual sem herdar ocorrências próprias. Ciclos não multiplicam evidências.
- Incidente é contado uma vez, mesmo com vários CNPJs; filiais contam uma raiz
  empresarial. Ocorrências confirmadas valem até expiração/revogação explícita,
  sem expirar automaticamente em 24h.

Exposição de 0–100 usa o maior entre **maior severidade ponderada + corroboração**
e **metade do maior untrust relacionado ponderado**. Corroboração acrescenta cinco
por incidente forte adicional, até 20; forte exige severidade ≥60 e peso do caminho
≥0,75. Empresas limpas não diluem a maior evidência. Truncamento suprime inferência
relacional incompleta, preserva evidência direta e marca histórico próprio incompleto
como desconhecido, em vez de zero.

| Modo | Efeito na decisão |
|---|---|
| `off` | Desativa a camada. |
| `shadow` — padrão | Calcula/grava; não altera pontos nem status. |
| `contribute` | Acrescenta `teto(exposição × 20 / 100)`, ponderado no fator `graph`, com teto 20; pode ajudar a atingir a rejeição geral por score. |

Em `contribute`, a ação direta propõe **somente 2FA** se houver: suspeita própria
agregada do titular ≥40 com controle próprio habilitado; ocorrência confirmada
própria de severidade ≥60; ou pelo menos dois incidentes fortes e exposição ≥60.
Peso `graph=0` desativa pontos/ação por vínculos, preservando suspeita própria agregada
e intervenções anteriores. Cadastro inicial vazio não fornece vínculos reais.
Fonte: [entity_risk.py](../src/entity_risk.py).
[Testes P07](testes-politicas.md#cobertura-p07).

## 3. Geolocalização, IP e aparelho

**Geolocalização:** campo opcional com latitude finita entre −90 e 90 e longitude
entre −180 e 180. É validado e armazenado. **Não há regra de raio/distância, tempo
de deslocamento, velocidade impossível, localização habitual, geofencing ou
cruzamento GPS/IP.** Não existe geolocalização separada do recebedor para comparação.
O horário do Pix não é combinado às coordenadas para produzir risco.

**IP:** obrigatório e sintaticamente válido IPv4/IPv6; armazenado sem pontuação por
reputação, VPN, proxy, país ou associação com a localização.

**`device_id`:** identificador do aparelho de origem informado pelo integrador,
não vazio, até 128 caracteres, com espaços externos removidos. Não há geração de
fingerprint, atestação de hardware ou comprovação de posse. Conta-se o identificador
como fornecido, sem inferir localização ou identidade física do equipamento.

| Regra | Condição padrão | Pontos |
|---|---|---:|
| <a id="r09"></a>R09 — Aparelho desconhecido | ≥ três aprovações do pagador em 30 dias, aparelho sem aprovação e valor ≥ R$ 500. | 20 |
| <a id="r10"></a>R10 — Aparelho compartilhado | ≥ três titulares distintos no mesmo aparelho em 24h, incluindo o atual. Várias contas do mesmo titular contam uma pessoa. | 30 |
| <a id="r11"></a>R11 — Múltiplos aparelhos | ≥ três aparelhos distintos do pagador em 24h, incluindo o atual, que deve ser desconhecido. Agrega suas contas e deduplica repetições. | 20 |

As três regras compartilham teto **40**. R10/R11 não têm piso de valor; familiaridade
não elimina compartilhamento. O mesmo aparelho também conecta nós do grafo e tem
trava de concorrência. Fonte: [schema](../src/schemas/pix.py),
[regras de aparelho](../src/risk/rules/device.py).

## 4. Demais regras transacionais

Valores são inteiros em centavos. Idade usa a abertura informada e a data do Pix;
sete dias completos deixam de ser conta recente. Todos os controles são avaliados.

| Regra | Condição padrão | Pontos / fator |
|---|---|---|
| <a id="r01"></a>R01 — Frequência | Cinco tentativas anteriores do pagador na janela inclusiva de 10 min; a atual é a sexta. | 80 / `activity` + rejeição obrigatória |
| <a id="r02"></a>R02 — Montante | Tentativas do pagador em 10 min + atual ≥ R$ 30 mil. | 80 / `activity` + rejeição obrigatória |
| <a id="r03"></a>R03 — Primeiro Pix | Nenhuma tentativa anterior, sem referência aprovada e valor ≥ R$ 500. | 30 / `exposure` + 2FA obrigatório |
| <a id="r04"></a>R04 — Referência insuficiente | Há tentativas, mas nenhuma referência aprovada; valor ≥ R$ 500. | 30 / `exposure` + 2FA obrigatório |
| <a id="r05"></a>R05 — Origem recente | Conta de origem com menos de sete dias; sem piso de valor. | 15 / `account` |
| <a id="r06"></a>R06 — Destino recente | Destino desconhecido, conta com menos de sete dias e valor ≥ R$ 500. | 15 / `counterparty` |
| <a id="r07"></a>R07 — Destinatário desconhecido | ≥ três aprovações do pagador em 30 dias, destino desconhecido e valor ≥ R$ 500. | 15 / `counterparty` |
| <a id="r08"></a>R08 — Desvio de perfil | Valor ≥ cinco vezes a média das últimas até dez aprovações; sem piso monetário. Compara inteiros: `valor × quantidade >= soma × multiplicador`. | 80 / `profile` |
| <a id="r12"></a>R12 — App noturno fora do hábito | Canal `app`, ignorando maiúsculas/espaços externos; Brasília UTC−3 em [20h,06h); valor ≥ R$ 500; ≥ três aprovações em 30 dias, nenhuma noturna; aparelho **ou** destino desconhecido. | 15 / `access_context` |
| <a id="r13"></a>R13 — Possível duplicidade | Mesma conta de origem/destino, valor igual e ID diferente; tentativa anterior aprovada/pendente em [evento−120s, evento]. Rejeição anterior não é elegível. | 30 / `duplication` |

Abaixo de R$ 500, ausência de referência não pontua; os demais controles continuam.
Trocar aparelho/data de abertura não esconde duplicidade. Outros canais não recebem
R12, mas mantêm os demais controles. A API não aplica limites bancários regulatórios
nem consulta blacklist externa de destino. Fonte: [avaliadores](../src/risk/rules).

## 5. Confiabilidade e suspeita própria

Não existe um score único de "conta confiável". Familiaridade, atenuação por relação,
suspeita própria e exposição societária têm funções distintas. Score próprio zero
significa ausência de evidência própria vigente, sem comprovar legitimidade.

<a id="p05"></a>

**P05 — Confiança contextual, habilitada:** exige ≥ cinco amostras do pagador,
≥ três da relação com o destino, em ≥ dois dias distintos de **recebimento** em
Brasília. Usa até 20 referências por conjunto em 30 dias. Valor de **50% a 200% da
mediana da relação**, inclusive, pode zerar somente R08. Mediana preserva meio
centavo por aritmética inteira. Amostra inválida, insuficiente ou micropagamentos
incompatíveis não concedem redução. Não elimina outras regras nem restrição já
acumulada; evidência e pontos anteriores ficam salvos.
[Fonte](../src/risk/contextual_trust.py) / [testes P05](testes-politicas.md#cobertura-p05).

<a id="p06"></a>

**P06 — `account_untrust`, habilitado:** soma evidência própria daquela conta em
24h pelo servidor, sem acrescentá-la ao score da transação. Somente R01, R02,
R08, R09, R10 e R11 são elegíveis; remapear fatores não muda a natureza da evidência.

- Limite forte elegível: incremento **25**.
- Nos demais casos, se score transacional ≥30: incremento
  `min(25, teto(contribuições elegíveis efetivas / 4))`; caso contrário, zero.
- ≥40 exige **2FA**; ≥60 indica **aviso ao banco**, sem enviá-lo.
- ≥80 e ≥quatro eventos podem rejeitar **apenas com bloqueio optativo habilitado**,
  desligado no padrão. Histórico já nessa faixa suprime novos incrementos mesmo
  com bloqueio desligado; a restrição não se renova por sua própria ação.
- Cada incremento expira individualmente; a exibição é limitada a 100. Apurar o
  histórico não relaxa rejeição/2FA de outra origem. Payload inválido e reenvio
  não criam pontos. Destino, grafo e ação de 2FA não realimentam o acumulado.

O titular pode agregar esses mesmos incrementos entre contas, conforme P07. Abrir
outra conta não transfere o acumulado da anterior para a nova conta; a camada do
titular mantém a visão conjunta. [Fonte](../src/controllers/account_untrust.py) /
[testes P06](testes-politicas.md#cobertura-p06).

## 6. Como os scores são gerados e decidem

| Indicador | Geração | Uso |
|---|---|---|
| `risk_score` | Regras acionadas, ponderação, atenuação e tetos; 0–100. | Decide o Pix, com prioridades abaixo. |
| `account_untrust.score` | Soma de incrementos próprios da conta em 24h; exibição até 100. | Pode exigir 2FA e indicar aviso; bloqueio optativo. |
| `entity_risk.own_entity.score` | Mesmos incrementos próprios agregados por documento entre contas. | Pode exigir 2FA em `contribute`. |
| `entity_risk.relationships.exposure_score` | Evidências societárias ponderadas e deduplicadas; 0–100. | Em `contribute`, pontos/2FA conforme P07. |
| `untrust_score` público | Previsão do grafo temporal ×100. | Em `contribute`, pode exigir 2FA conforme P09; não é o acumulado da conta. |

<a id="p02"></a>

**P02 — Pontos:** `piso(peso_da_regra × percentual_do_fator / 100)`, seguido do teto
do fator e soma final até 100. Percentuais padrão são 100%; dentro do fator, os
maiores sinais consomem o teto primeiro e o código desempata. Várias regras de um
fator continuam sendo um único fator positivo para decidir rejeição.

| Fator | exposure | activity | account | counterparty | profile | device | access_context | duplication | graph optativo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Teto padrão | 80 | 80 | 15 | 25 | 80 | 40 | 15 | 30 | 20 |

<a id="p01"></a>

**P01 — Prioridade:** limite forte → rejeita; depois score ≥80 com ≥dois fatores
positivos → rejeita; depois ausência de perfil com valor ≥R$500 ou score ≥30 →
2FA; demais → aprova. Um fator isolado com 80 gera 2FA. Limites fortes e exigência
por ausência de referência sobrevivem a pesos zero. Conta/titular só podem agravar
a decisão. Faixas `low` <30, `elevated` 30–79 e `high` ≥80 são classificações do score,
não probabilidades. [Fonte](../src/risk/scoring.py) /
[testes P01](testes-politicas.md#cobertura-p01) / [P02](testes-politicas.md#cobertura-p02).

Exemplos: aparelho novo 20 → aprova; aparelho novo 20 + destino desconhecido 15 →
35/2FA; perfil 80 isolado → 2FA; perfil 80 + origem recente 15 →95/rejeita.
Com acumulado próprio 40, um novo Pix de score zero ainda pode exigir 2FA.

## 7. Grafo e sua relação com confiabilidade

<a id="p09"></a>

**P09 — Modelo temporal v2:** conta, titular e aparelho são nós distintos. As seis
relações representam pagar/receber, usar aparelho/ser usado e possuir conta/pertencer
ao titular. Entrada e saída têm atributos separados: valor, idades, frequência,
titulares por aparelho, suspeita própria, risco dos contatos e repasses rápidos.
Geolocalização e IP não são atributos desse modelo.

Duas camadas agregam mensagens por relação com pesos treinados em dados sintéticos.
Uma saída sigmoide gera valor em [0,1], multiplicado por 100; não é probabilidade
calibrada. A consulta usa dois saltos, até 300 eventos em 30 dias e 100 documentos,
mais até 300 incrementos próprios em 24h. Precisa de ≥três eventos não rejeitados;
conexões históricas de pagamento/aparelho decaem com meia-vida de 12h. Rejeições
podem carregar evidência própria, mas não criam fluxo de pagamento.

**Tratamento da saída:** `GNN_V2_MODE=shadow` observa e `off` desativa; o padrão
`contribute` do protótipo pode elevar `approved` para `two_factor_required` com
score ≥75,0977, manifesto válido e modelo/política correspondentes à avaliação.
O grafo roda depois das outras camadas, com **zero pontos e nenhuma rejeição própria**.
Score alto não torna conta suspeita no acumulado; score baixo não concede confiança,
não atenua regras e não remove 2FA/rejeição. Cadastro societário P07 é outra camada:
seu fator chamado `graph` não é contribuição dessa rede neural.

Detalhes e limites da validação sintética: [contribuição do GNN](gnn-contribution.md).

Histórico truncado/inválido gera abstenção sem score parcial; modelo ausente fica
indisponível; falha tratada de inferência preserva as regras. Falha SQL propaga e
impede sucesso/commit. Sem avaliação, `untrust_score` é omitido; score numérico zero
é exibido. Hash, modo, cobertura e diagnóstico permanecem na auditoria.
[Serviço](../src/gnn/temporal_service.py), [modelo](../src/gnn/temporal_model.py) /
[testes P09](testes-politicas.md#cobertura-p09).

<a id="p08"></a>

**P08 — Indicadores financeiros observacionais:** usam tentativas não rejeitadas,
deduplicadas, em 24h de evento/recepção, sem autorrelações. Por direção, selecionam
até dez contatos e registram máximo, três maiores suspeitas, desconhecidos e fração
com suspeita ≥40. Repasse exige saída depois da entrada em até 30 min, entre 80% e
125% do recebido, para destino diferente do remetente; uma entrada suporta um par.
Dois pares e destino com suspeita ≥40 marcam indicador composto. Contribuição é
zero e truncamento não vira estatística parcial. Atributos análogos alimentam o
modelo temporal sem criar regra automática de rejeição.
[Fonte](../src/financial_features.py) / [testes P08](testes-politicas.md#cobertura-p08).

## 8. Controles operacionais e hipóteses experimentais

| Política | Tratamento implementado |
|---|---|
| <a id="p04"></a>P04 — Configuração | Operador controla pesos, fatores, janelas e versão; pedido não escolhe parâmetros. Configuração parcial mantém padrões; campo/tipo desconhecido ou incoerência falha. Pesos por regra 0–100, percentuais 0–200, tetos 1–100, limiares `0 < 2FA < rejeição <=100`; quantidades/janelas positivas. Mudança exige versão/reinício e não altera snapshots anteriores. |
| <a id="p10"></a>P10 — Contrato | Valor inteiro positivo até BIGINT; ID válido de 1–128 caracteres; datas ISO com fuso, abertura não posterior ao Pix; campos extras recusados; participante destino obrigatório com oito dígitos. POST analisa/persiste; GET recupera; inválido 400, ausente 404. Health verifica processo e ready consulta tabela. Não há execução de 2FA, liquidação ou gestão de limites bancários. |
| <a id="p11"></a>P11 — Integridade | Mesmo ID/conteúdo normalizado recupera original; conteúdo diferente gera 409 sem sobrescrever. Travas por ID, documento pagador e aparelho preservam contagens/incrementos concorrentes. Nova política, modo ou cadastro não recalcula análise salva. |
| <a id="p12"></a>P12 — Auditoria | Payload/hash, identidades, política e evidências persistidos; trigger impede UPDATE/DELETE na operação normal, sujeito às permissões do banco. HTTP expõe resumo; detalhes acrescentam aliases efetivos/controles obrigatórios, sem pesos internos. Tempo é medido antes da inserção e preservado no replay. Legado é projetado sem mutação. |
| <a id="p13"></a>P13 — Transporte | JSON obrigatório no POST, até 32 KiB reais, prazo total padrão 10s; falhas 415/413/408 e tamanho malformado 400. ID de requisição, no-store, nosniff e no-referrer; erro inesperado 500 genérico sem conteúdo sensível. SQLAlchemy falha 503 orientando repetir ID. Rotas não exigem token. A suíte catalogada verifica propagação SQL/ausência de commit, sem cenário HTTP 503 dedicado; readiness é testado disponível. |
| <a id="p14"></a>P14 — Experimentos | Propostas offline só simulam approved→2FA, sem pontos, rejeições ou suspeita própria. Proposta corroborada exige score disponível ≥ limiar, valor ≥ piso e ≥ dois pares rápidos. Calibra antes do teste, sem diluir fricção com legítimos já restritos; ausência de ambas as classes causa abstenção. Critérios por semente: ganho ≥5%, limite superior Wilson 95% da fricção ≤1%, pior categoria legítima ≤5%, zero rejeição adicional e cobertura ≥95%. São critérios sintéticos, não autorização automática. |

Experimento de vizinhos com diluição, propostas de 2FA e retreino para falsos
positivos ficam separados da API: não substituem automaticamente seu modelo padrão.
Treino/validação/teste separam identidades e tempo; pesos/schema, paridade de inferência
e relatórios têm verificações próprias. Cenários SQL de validação usam rollback
externo. Os exemplos e limiares são hipóteses, sem comprovar eficácia em fraude real.
Consulte [validação v9](gnn-v9-validation.md), [falsos positivos](gnn-false-positives.md)
e a [matriz política → testes](testes-politicas.md#matriz-inversa-política--testes-que-a-verificam).
