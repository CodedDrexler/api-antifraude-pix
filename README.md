# Pix Antifraude — Bootcamp QI Tech 2026

**Integrantes:** Vinícius Guimarães Drexler e Wallace Dametto Teixeira.

API em Python 3.12, FastAPI e PostgreSQL 16 que avalia um Pix e retorna
`approved`, `two_factor_required` ou `rejected`, preservando decisão e evidências.
Os scores são indicadores heurísticos; não representam probabilidade de fraude.

## Escopo desta documentação

Esta atualização publica **somente o README**. O código publicado que a antecede,
na revisão `1ca3e5c`, usa **`pix-score-v8`**. O catálogo abaixo consolida a análise
da revisão local **`pix-score-v9`** e da integração posterior do grafo; essas
alterações de implementação ainda não estão incluídas neste commit documental.

| Comportamento | Código publicado v8 | Revisão local analisada v9 |
|---|---|---|
| Ausência de referência | Primeiro Pix/referência ausente exigem 2FA independentemente do valor. | Exigem 2FA por esse motivo somente a partir de R$ 500; demais controles continuam. |
| Formação inicial do perfil | Pode usar a primeira tentativa pendente como referência provisória. | Usa somente aprovações; pendências nunca formam referência. |
| Grafo temporal v2 | `shadow` ou `off`, sem intervenção. Há também implementação legada v1. | V2 substitui v1; integração posterior admite `contribute`, limitado a aprovação → 2FA. |
| Detalhes HTTP | Exibe metadados/evidências conforme contrato v8. | Resumo público; `include_details=true` acrescenta apenas nomes das regras. |

Executar a branch publicada mantém o comportamento v8. A documentação de uma
política nova não a ativa nem substitui código, configuração ou modelos.

## Conta enviadora, receptora e titular

O objeto da decisão é **um Pix da origem para o destino**, não uma classificação
permanente de ambas as contas.

| Elemento | Política de tratamento |
|---|---|
| Conta de origem | Avalia idade, atividade, perfil de valores, aparelhos e suspeita própria acumulada. |
| Conta de destino | Idade e familiaridade podem restringir o Pix; isso não gera suspeita própria para o remetente nem um novo incremento próprio para a conta receptora. |
| Relação pagador → destinatário | Aprovações, valores habituais e repetição são direcionais. A→B não concede automaticamente familiaridade a B→A. |
| Identidade da conta | Instituição, agência, número e documento; abertura e aparelho ficam fora. Informar instituição antes omitida pode mudar a identidade considerada. |
| Histórico do titular | Frequência, perfil, familiaridade e diversidade agregam contas do mesmo CPF/CNPJ. O acumulado próprio de cada conta continua separado. |

Receber um Pix não estabelece perfil de envio. Tentativa aprovada ou pendente
não comprova liquidação; solicitar 2FA não comprova sua execução.

## CPF, CNPJ e vínculos societários

As regras transacionais são iguais para CPF→CPF, CPF→CNPJ, CNPJ→CPF e CNPJ→CNPJ.
Documentos são normalizados para 11/14 dígitos, com validação de formato, sem
consulta cadastral nem verificação dos dígitos verificadores.

- Contas do mesmo documento compartilham histórico por titular. CPF e CNPJ são
  identidades distintas, sem fusão de suas evidências próprias.
- Sociedade exige cadastro verificado do operador; transferência, nome semelhante
  ou aparelho compartilhado não comprovam vínculo. Não há consulta automática à Receita/QSA.
- Papéis: controlador/beneficiário final **1**; administrador **0,5**; minoritário
  **0,2**; contador **0**. Papéis fracos não servem de ponte entre empresas.
- Busca até **três arestas societárias e 100 entidades**, respeitando verificação,
  conhecimento e validade temporal. Associação à empresa de uma ocorrência deve
  respeitar também a época do incidente. Empresa nova pode ter exposição pelo
  controlador atual sem receber ocorrências próprias.
- Incidente conta uma vez, mesmo envolvendo vários CNPJs; filiais contam uma raiz
  empresarial. Ocorrências confirmadas valem até expiração/revogação explícita,
  sem expirar automaticamente em 24h. Ciclos não multiplicam evidências.

A exposição relacional usa o maior entre: maior severidade ponderada mais
corroboração; ou metade do maior untrust relacionado ponderado. A corroboração
acrescenta cinco por incidente forte adicional, até 20; forte exige severidade
≥60 e peso do caminho ≥0,75. A exposição final é limitada a 100. Empresas limpas
não diluem a evidência mais forte; truncamento impede inferência relacional
incompleta e preserva evidência direta.

`entity_risk` observa em `shadow`, por padrão. Em `contribute`, pode acrescentar
`ceil(exposição × 20 / 100)` ao fator `graph`, sujeito à ponderação e teto 20.
A ação direta propõe somente 2FA por: suspeita própria do titular ≥40 com controle
habilitado; ocorrência confirmada própria ≥60; ou ≥dois incidentes fortes e exposição
≥60. Peso `graph=0` desativa pontos/ação por vínculos, preservando o controle próprio
agregado e restrições anteriores. Cadastro vazio não oferece vínculos reais.

## Geolocalização, IP e aparelho

| Dado | Implementação |
|---|---|
| Geolocalização | Opcional; latitude finita entre −90 e 90 e longitude entre −180 e 180. Validada e armazenada, sem pontuar. |
| Distância e tempo de deslocamento | Não há raio, velocidade impossível, localização habitual, geofencing ou cruzamento GPS/IP. Não há localização separada do recebedor. |
| IP | Obrigatório e válido IPv4/IPv6; sem pontuação por reputação, VPN, proxy ou país. |
| `device_id` | Identificador de origem fornecido pelo integrador, não vazio, até 128 caracteres e com espaços externos removidos. Não há fingerprint próprio ou atestação de hardware. |

Regras de aparelho estão na tabela abaixo. Geolocalização e IP não são atributos
do modelo temporal analisado; o aparelho conecta nós do grafo e tem trava para
serializar análises concorrentes.

## As 13 regras — referência v9

Valores de entrada/configuração são inteiros em centavos. "Conhecido" significa
aprovação local do pagador com aquele aparelho/destino em **30 dias**.

| Regra | Condição padrão | Pontos / fator |
|---|---|---|
| Frequência | Cinco tentativas anteriores do pagador em 10 min; a atual é a sexta. | 80 / `activity` + rejeição obrigatória |
| Montante | Tentativas do pagador em 10 min + atual ≥R$30 mil. | 80 / `activity` + rejeição obrigatória |
| Primeiro Pix | Nenhuma tentativa anterior, sem referência aprovada e valor ≥R$500. | 30 / `exposure` + 2FA obrigatório |
| Referência insuficiente | Há tentativas, mas nenhuma referência aprovada; valor ≥R$500. | 30 / `exposure` + 2FA obrigatório |
| Origem recente | Conta com menos de sete dias; sem piso de valor. | 15 / `account` |
| Destino recente | Destino desconhecido, conta com menos de sete dias e valor ≥R$500. | 15 / `counterparty` |
| Destinatário desconhecido | ≥3 aprovações do pagador em 30 dias, destino desconhecido e valor ≥R$500. | 15 / `counterparty` |
| Desvio de perfil | Valor ≥5 vezes a média das últimas até dez aprovações, sem corte por dias; uma aprovação já forma referência. | 80 / `profile` |
| Aparelho desconhecido | ≥3 aprovações do pagador em 30 dias, aparelho desconhecido e valor ≥R$500. | 20 / `device` |
| Aparelho compartilhado | ≥3 titulares distintos no aparelho em 24h, incluindo o atual; várias contas do mesmo titular contam uma pessoa. | 30 / `device` |
| Múltiplos aparelhos | ≥3 aparelhos distintos do pagador em 24h, incluindo o atual desconhecido; repetições são deduplicadas. | 20 / `device` |
| App noturno fora do hábito | Canal `app`, ignorando maiúsculas/espaços externos, em [20h,06h) de Brasília; valor ≥R$500; ≥3 aprovações em 30 dias, nenhuma noturna; aparelho ou destino desconhecido. | 15 / `access_context` |
| Possível duplicidade | Mesmas contas de origem/destino, mesmo valor e outro ID; tentativa anterior aprovada/pendente em [evento−120s, evento]. | 30 / `duplication` |

Frequência, montante e diversidade contam também rejeições e pendências. Perfil e
familiaridade usam aprovações; na v9, pendências nunca criam/elevam referência.
Idade usa abertura informada e data do Pix; sete dias completos deixam de ser conta
recente. Duplicidade não usa rejeição anterior e não é escondida por troca de aparelho
ou abertura. Outros canais mantêm os controles, exceto o sinal específico de app.
Essas regras não verificam limites bancários regulatórios ou blacklist externa.

## Geração dos scores e prioridade de decisão

| Indicador | Origem | Uso |
|---|---|---|
| `risk_score` | Regras, ponderação, atenuação e tetos; 0–100. | Decide o Pix conforme prioridades abaixo. |
| `account_untrust` | Incrementos próprios da conta recebidos em 24h. | Pode exigir 2FA e indicar aviso; bloqueio optativo. |
| Suspeita própria do titular | Mesmos incrementos agregados entre contas do documento. | Pode exigir 2FA em `entity_risk=contribute`. |
| Exposição societária | Ocorrências e vínculos verificados, ponderados e deduplicados. | Pode acrescentar pontos/2FA conforme o modo da camada. |
| Score temporal do grafo | Saída da rede ×100; na revisão local é exposta como `untrust_score`. | Observa ou propõe 2FA conforme versão/modo; não é o acumulado próprio. |

Pontos por regra: `floor(peso × percentual_do_fator / 100)`. Percentuais padrão
são 100%. Dentro do fator, sinais maiores consomem o teto primeiro; código da regra
desempata. A soma final fica limitada a 100.

| Fator | exposure | activity | account | counterparty | profile | device | access_context | duplication | graph optativo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Teto | 80 | 80 | 15 | 25 | 80 | 40 | 15 | 30 | 20 |

| Prioridade v9 | Condição | Resultado |
|---|---|---|
| 1 | Limite forte de frequência/montante. | `rejected` |
| 2 | Score ≥80 e ≥dois fatores positivos. | `rejected` |
| 3 | Sem perfil aprovado e valor ≥R$500, ou score ≥30. | `two_factor_required` |
| 4 | Demais casos. | `approved` |

Um fator isolado com 80 exige 2FA. Limites fortes e exigência por ausência de
referência sobrevivem a pesos zero. Conta/titular e contribuição habilitada do
grafo só podem agravar a intervenção. Faixas `low` <30, `elevated` 30–79 e `high`
≥80 descrevem o score; não são probabilidades ou classificação definitiva de fraude.

Exemplos: aparelho novo 20 → aprova; aparelho 20 + destino desconhecido 15 →35/2FA;
perfil 80 isolado →2FA; perfil 80 + origem recente 15 →95/rejeita.

## Confiabilidade, atenuação e suspeita acumulada

Não existe um score único e permanente de conta confiável. Há três mecanismos:

1. **Familiaridade:** aprovação local torna aparelho/destino conhecidos em 30 dias.
2. **Confiança contextual:** com ≥5 amostras do pagador, ≥3 da relação em ≥2 dias
   distintos de recebimento em Brasília, valor entre 50% e 200% da mediana pode
   zerar somente o desvio de perfil. Usa até 20 referências por conjunto em 30 dias,
   sem limite forte; referência inválida/insuficiente ou micropagamento incompatível
   não concede redução. Preserva as outras regras e a evidência original.
3. **Suspeita própria da conta:** frequência, montante, perfil e os três sinais de
   aparelho podem acrescentar evidência; destino, primeiro Pix, idade da conta,
   horário, duplicidade, grafo e o próprio pedido de 2FA não realimentam esse acumulado.

Para suspeita própria: limite forte elegível soma **25**; nos demais casos, com
score transacional ≥30, soma `min(25, ceil(contribuições próprias efetivas / 4))`;
abaixo disso, zero. Elegibilidade segue a regra, mesmo se seu fator for remapeado.

| Acumulado próprio | Consequência |
|---|---|
| ≥40 | Exige 2FA, mesmo se o Pix atual tiver score zero. |
| ≥60 | Indica aviso ao banco, sem enviá-lo; registra o cruzamento do limiar. |
| ≥80 e ≥4 eventos | Pode rejeitar se `rejection_enabled=true`; desligado no padrão. |

Incrementos expiram individualmente após 24h pelo relógio do servidor; a exibição
é limitada a 100. Histórico já em ≥80 e ≥4 eventos suprime novos incrementos,
mesmo com bloqueio desligado, para não renovar indefinidamente a restrição.
O acumulado não é somado ao score transacional nem relaxa decisão anterior.
Outra conta não recebe o acumulado da primeira, mas `entity_risk` pode manter a
visão própria conjunta do titular. Zero significa ausência de evidência vigente,
sem comprovar legitimidade.

## Grafo, recebimentos e repasses

O v2 distingue conta, titular e aparelho; relações de pagar/receber, usar aparelho
e possuir conta têm direção explícita. Analisa valores, idades, atividade, titulares
por aparelho, suspeita própria, contatos e repasses. Não deduz sociedade a partir
de um Pix. Duas camadas agregam mensagens por relação; a saída sigmoide é
multiplicada por 100 e não é calibrada como probabilidade de fraude.

O recorte usa até dois saltos, 300 eventos em 30 dias e 100 documentos, mais até
300 incrementos próprios em 24h. Precisa de ≥3 eventos não rejeitados; arestas
históricas de pagamento/aparelho têm meia-vida de 12h. Rejeições podem conter
evidência própria, mas não criam fluxo financeiro.

Indicadores financeiros separam entradas/saídas em 24h, até dez contatos por direção,
máximo, três maiores suspeitas e fração com suspeita ≥40. Repasse exige saída após
entrada em até 30 min, entre 80% e 125% do recebido, para destino diferente do
remetente; uma entrada suporta um par. Esses indicadores não acrescentam pontos.

| Versão / modo | Tratamento da saída |
|---|---|
| V2 publicado v8: `shadow` / `off` | Observa ou desativa; nunca altera status. |
| V2 local posterior: `shadow` / `off` | Mantém observação ou desativação. |
| V2 local posterior: `contribute` | No protótipo, pode elevar somente `approved` para `two_factor_required` com score ≥75,0977 e modelo/política compatíveis com manifesto avaliado. |

O corte local corresponde a `0.750977`, método `score_only_2fa/confidence_budget`.
Manifesto ausente/inválido, hash de modelo ou política divergente impedem ação.
A contribuição não altera `risk_score`, não rejeita sozinha, não remove restrição,
não gera suspeita própria nem aviso bancário. Score baixo não concede confiança
ou atenua regras. O fator societário `graph` é independente dessa rede neural.

Histórico insuficiente/truncado/inválido e falha tratada de inferência causam
abstenção, sem score parcial ou nova intervenção. Sem avaliação, a revisão local
omite `untrust_score`; zero numérico é válido. Falha SQL continua sendo erro, não
aprovação silenciosa. Avaliações sintéticas e retreinos não publicam nem ativam
automaticamente uma nova política; o modo local ativo foi uma escolha explícita
posterior para o protótipo, ainda fora do código publicado neste commit.

## Contrato, auditoria e configuração

- Mesmo ID e conteúdo normalizado recuperam a decisão original; conteúdo diferente
  gera **409** sem sobrescrever. Formatos equivalentes de documento/fuso normalizam
  para o mesmo conteúdo. GET/reenvio preservam política, modo e evidências originais.
- Travas por ID, pagador e aparelho serializam tentativas concorrentes. Histórico
  financeiro exclui eventos futuros/informação ainda não recebida; evidência própria
  usa o servidor, impedindo que um Pix retrodatado apague o acumulado vigente.
- Banco guarda pedido, hash, identidades, decisão e evidências. Trigger impede
  UPDATE/DELETE na operação normal, sujeito às permissões do banco.
- Entrada exige valor inteiro positivo até BIGINT, datas ISO com fuso e abertura
  não posterior ao Pix; participante do destino obrigatório com oito dígitos.
  Campos extras e inválidos são recusados sem consumir ID.
- Transporte exige JSON, até 32 KiB reais e prazo padrão 10s; erros 415/413/408,
  Content-Length inválido 400, entrada 400, ausente 404 e falha de banco 503. Após 503,
  repita o ID. Há no-store, nosniff, no-referrer e identificador de requisição;
  erro inesperado 500 não expõe conteúdo sensível. Rotas Pix não exigem token.
- Operador configura pesos, fatores e janelas; cliente não negocia limites no pedido.
  Pesos por regra 0–100, percentuais 0–200, tetos 1–100; `0 < 2FA < rejeição <=100`.
  Configuração parcial mantém padrões; incoerência/campo desconhecido falha na carga.
  Alteração exige versionamento/reinício e não reescreve decisões antigas.

## Executar o código publicado

Requer Docker Desktop com Docker Compose. Na raiz:

```powershell
docker compose up --build -d --wait
```

Abra o [Swagger](http://127.0.0.1:8000/docs) e use um ID novo. A revisão publicada
continua v8, incluindo seu início sem histórico descrito no quadro de versões.
Porta/modos podem ser definidos em `.env`, conforme [.env.example](.env.example).
`docker compose down` preserva o volume `pix_data`.

| Método e rota | Resultado |
|---|---|
| `POST /pix/transaction` | Analisa/grava pedido válido inédito. |
| `GET /pix/transaction/{id}` | Recupera a decisão pelo ID enviado. |
| `GET /health` ou `/health_check` | Verifica processo. |
| `GET /ready` | Verifica acesso ao banco/tabela. |

Veja o [pedido de exemplo](examples/pix.json): `150000` centavos = R$1.500.
Sem Docker: Python 3.12/PostgreSQL 16, `pip install -r requirements-dev.txt`,
[schema inicial](database/database.sql), `DATABASE_URL` com `postgresql+psycopg2://`,
`RISK_POLICY_PATH=config/risk-policy.json` e `python -m uvicorn src.app:app`.
Em base existente, aplique as [migrações](database/migrations) pendentes; não apague
o volume para atualizar schema.

## Testes e limites da avaliação

Na revisão publicada, use `.\testar.bat --no-pause` conforme o
[script versionado](testar.bat), que prepara API/banco isolados e executa testes,
lint e formatação. GitHub Actions também executa as verificações em push/PR.
Os testes cobrem fronteiras, combinação de fatores, concorrência, persistência,
replay, recortes temporais e separação entre risco próprio e relacional.

Esta publicação documental não reexecuta a suíte de negócio. Relatórios e
inventários de outras revisões são registros históricos, não cobertura automática
da revisão atual.
Dados sintéticos não comprovam eficácia ou taxa de falsos positivos em Pix real.

Referências disponíveis no código publicado: [regras](docs/risk-scoring.md),
[confiança contextual](docs/contextual-trust.md), [acumulado](docs/account-untrust.md),
[titular e vínculos](docs/entity-risk.md), [grafo temporal](docs/graph-v2-api.md),
[experimentos](docs/graph-v2-experiment.md) e [arquitetura](docs/architecture.md).
Esses documentos acompanham a revisão publicada e podem conter contratos anteriores
à síntese v9 deste README. O projeto não executa 2FA, liquidação, envio de avisos
ou gestão de limites bancários; aprovação local não confirma pagamento.
