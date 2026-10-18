# Casos parecidos, decisões diferentes

Revisão de 17/10/2026, política `pix-score-v7`. A base do projeto é adequada
para demonstração: evidências persistidas, idempotência, limites fortes e
acumulado temporal separado do score da transação. A revisão encontrou e
corrigiu inconsistências na elegibilidade do acumulado e na avaliação offline.
Isso melhora a consistência; não comprova detecção de fraude real.

## Correções

O acumulado selecionava evidências pelo grupo configurável da regra.
Ao mover `first_transaction`, `insufficient_amount_history` ou
`possible_duplicate_payment` para `device`, cada um passava a somar 8 pontos
de suspeita. Mover a regra de desvio de perfil para `exposure` fazia seus
20 pontos de incremento desaparecerem, mesmo mantendo o score transacional 80.
Os quatro testes reproduziram essas falhas antes da correção.

Agora a elegibilidade segue códigos explícitos das regras de frequência,
montante, perfil, dispositivos e destinatário. A contribuição continua
respeitando pesos e tetos configurados. Ausência de histórico, idade da conta
de origem, horário, duplicidade e GNN não viram evidência própria de suspeita
apenas por mudar de grupo. Os limites fortes preservam seu tratamento especial.

O simulador `scripts/evaluate_untrust.py` não consultava duplicidade e ordenava
empates de horário pelo texto do ID. Agora considera pagamentos aprovados ou
pendentes dentro da janela inclusiva de 120 segundos, mantém a ordem de chegada
nos empates e reproduz repetição e conflito de IDs. Também informa a origem
real da referência de perfil.

## O que os pares verificam

| Mudança isolada ou contexto comparado | Resultado esperado |
|---|---|
| Mesmo valor e desvio de perfil, destinatário conhecido ou desconhecido | Score 80: 2FA; score 95 com segundo fator: rejeição |
| Mesmo Pix de R$ 500, referências médias de R$ 200 ou R$ 100 | Score 0 e aprovação; score 80 e 2FA |
| Aparelho novo sozinho ou junto de destinatário novo | Score 20 e aprovação; score 35 e 2FA |
| Mesmo aparelho com dois ou três titulares | Sem sinal de compartilhamento; score 30 e 2FA |
| Pix limpo idêntico, acumulado 39 ou 40 | Aprovação ou 2FA, mantendo score transacional 0 |
| Mesmo pagamento a 120 s ou 120 s + 1 microssegundo | Possível duplicidade e 2FA; aprovação fora da janela |
| Evidência a 24 h − 1 microssegundo ou exatamente 24 h | Acumulado 40 e 2FA; evento expira, acumulado 20 e aprovação |
| Três sinais de dispositivo, com 70 pontos brutos | Teto de 40; incremento de 10, sem somar sinais correlacionados novamente |
| Alterar ID novo, IP, localização ou representação equivalente de fuso | Mesma avaliação com o mesmo contexto histórico |
| GNN desligado, em observação ou contribuindo | Pontos do GNN e a própria restrição não alimentam o incremento independente |

As verificações de ID novo usam um contexto fixo. Ao enviar outro pedido à API,
a tentativa anterior passa a fazer parte do histórico e pode acionar duplicidade.

## Validação executada

Referência antes das alterações: **365 testes aprovados**. Resultado final:
**398 testes aprovados, nenhum ignorado**, incluindo **33 novos casos**.
Lint e formatação passaram em 64 arquivos Python.

`tests/test_untrust_contrasts.py` verifica causas de divergência, invariâncias,
tetos e separação entre GNN e suspeita acumulada. `tests/test_untrust_replay.py`
compara 13 sequências com o controlador e PostgreSQL reais. Em cada etapa,
compara decisão, score, regras, histórico, perfil, acumulado, aviso e política
do motor. O relógio de recebimento é controlado apenas no teste, seguindo os
instantes de chegada simulados. A gravação e a recuperação da decisão também
são verificadas. Há ainda um caso de conflito de ID e dois testes do relatório.

O JUnit desta execução está em `tmp/untrust-contrasts.xml` (arquivo local ignorado
pelo Git). Para reproduzir a suíte completa, use `.\testar.bat --no-pause`.
Para rodar apenas os novos casos no ambiente de testes:

```powershell
docker compose --profile test run --rm tests pytest -q tests/test_untrust_contrasts.py tests/test_untrust_replay.py
```

## Efeito do acumulado na amostra sintética

O relatório [untrust-synthetic-v1.metrics.json](../models/untrust-synthetic-v1.metrics.json)
foi recalculado para 150 cenários de validação e 200 de teste. Cada cenário é
executado com e sem acumulado, com GNN desligado. Rótulos vêm do gerador.

| Efeito adicional sobre o cenário | Validação | Teste |
|---|---:|---:|
| 2FA em casos legítimos | 3 | 1 |
| Rejeições legítimas, padrão somente 2FA | 0 | 0 |
| Desafios ou rejeições adicionais em fraude sintética | 0 | 0 |
| Rejeições legítimas, bloqueio optativo ativado | 3 | 4 |
| Indicações de aviso, padrão | 24 | 21 |

`decision_transitions` separa mudanças por rótulo; `changed_examples` mostra
até 12 exemplos por amostra, com scores, perfil, origem da decisão e evidências.
`transaction_evidence_changed` indica diferenças nas regras, referência média
ou número de aprovações entre as duas execuções.

No cenário `validation`, seed 65, o mesmo Pix passa de score 0 para 80 porque
a exigência de 2FA em operações anteriores muda as aprovações disponíveis para
o perfil: a média fica em 2.869 centavos, contra 38.300 sem acumulado.
No cenário `test`, seed 16, o score permanece 0 e o perfil é igual nas duas
execuções; o acumulado 60 é a causa direta do 2FA. Assim, uma diferença final
de decisão não deve ser atribuída automaticamente ao score do Pix.

O bloqueio por acumulado permanece desativado: nesta amostra adiciona rejeições
legítimas sem ganho de detecção. Mesmo no padrão de 2FA, ainda não há evidência
de ganho adicional contra fraude. Sem resultados confirmados de autenticação,
liquidação e fraude, não há base para calibrar os limiares ou afirmar que
operações com sinais iguais podem ser separadas corretamente por intenção.
Os dados são sintéticos e ambos os grupos já foram inspecionados; não são uma
avaliação final independente nem estimativa de desempenho em produção.

Decisões antigas são preservadas com sua política original. A versão v7 afeta
novas análises; incrementos anteriores não são recalculados e expiram na janela
original. Para uma demonstração sem mistura de versões, utilize o ambiente
isolado criado por `testar.bat`.
