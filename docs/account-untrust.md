# Desconfiança acumulada por conta (`account_untrust`)

Implementação atual: `pix-score-v8`. O indicador usa análises locais recentes para
exigir verificação adicional quando uma conta repete comportamentos de risco.
Não é uma probabilidade, uma lista de fraudadores nem confirmação de fraude.

## Identidade, evidências e janela

A conta é identificada por instituição quando informada, agência, número e documento normalizado.
A instituição da origem não é obrigatória no contrato; a identidade não é global.
A data de abertura não faz parte da identidade: alterá-la não zera o acumulado.
Os controles existentes por documento continuam reunindo contas do mesmo pagador;
o `account_untrust` é específico da conta. A identidade vem de um integrador
confiável; em produção, precisa corresponder ao cadastro bancário autenticado.

Cada nova análise elegível grava um incremento na própria decisão imutável.
A soma usa `created_at`, capturado pelo servidor após obter as travas, dentro da
janela `(agora − 24 horas, agora]`. Eventos futuros ficam fora. Alterar o horário
do Pix não remove as evidências já recebidas. Ao sair da janela, cada incremento
expira; não existe uma marca permanente na conta.

O cálculo usa apenas evidências próprias da transação, antes do GNN e antes de
aplicar o acumulado. As contribuições elegíveis são volume/frequência, perfil de
valores e dispositivos. Destinatário novo/desconhecido não alimenta a suspeita própria.
Primeiro Pix, idade da conta e horário,
isoladamente, não criam desconfiança acumulada.

Desde a v7, a elegibilidade segue os códigos das regras, independentemente do grupo
configurado. Mover primeiro Pix, histórico insuficiente ou duplicidade para outro
grupo não cria suspeita; mover desvio de perfil não remove sua elegibilidade.
Os pontos continuam respeitando pesos e tetos. Veja a
[revisão com testes de casos parecidos](decision-contrasts.md).

Na v8, somente incrementos com `evidence_version=sender-evidence-v2` entram nas
consultas de acumulado, titular e grafo temporal. O legado continua auditável,
mas não transporta contribuições ambíguas de destinatário para a suspeita própria.
A nova janela é formada por análises v8. O [Cofre contextual](contextual-trust.md)
pode reduzir exclusivamente a anomalia de perfil antes de calcular o incremento.

- Com limite forte da transação: incremento de até 25 pontos.
- Sem limite forte: exige score transacional de pelo menos 30; soma as
  contribuições elegíveis, divide por 4 com arredondamento para cima e limita a 25.
- Sinais fracos isolados abaixo de 30, payload inválido e repetição do mesmo ID:
  nenhum incremento adicional.
- Uma restrição ativa a partir de 80 com quatro eventos suspende novos incrementos,
  inclusive tentativas repetidas bloqueadas por outros controles. Isso evita
  renovar a restrição indefinidamente apenas por novas tentativas durante a restrição.
- Uma operação sem risco não apaga evidências. A recuperação é temporal;
  uma sequência de valores pequenos não limpa imediatamente a conta.

O score exibido é `min(100, soma dos incrementos ativos)`. Os incrementos originais
ficam preservados para que o vencimento de um evento não apague o peso dos demais.
O mesmo lock por pagador protege leitura, avaliação e gravação contra concorrência.
Só há resposta de sucesso depois do commit. Falha de banco não vira aprovação.

## Ações padrão e aviso

| Acumulado | Ação adicional |
|---|---|
| 0–39 | Nenhuma |
| 40–59 | Exigir 2FA |
| 60–79 | Exigir 2FA e indicar aviso ao banco |
| 80–100 | Manter 2FA e aviso; bloqueio pelo acumulado é optativo |

`untrust.rejection_enabled=false` é o padrão. Quando explicitamente ativado,
80 pontos e pelo menos quatro eventos de risco permitem `rejected` pelo acumulado.
Os limites fortes e rejeições por risco da transação continuam funcionando.
O acumulado só aumenta a exigência; nunca transforma uma rejeição em aprovação.

As duas medidas são separadas: `risk_score` descreve a transação;
`account_untrust.score` descreve o histórico recente da conta. Não se somam
nem contam como fatores independentes. Uma transação com score 0 pode exigir 2FA
por histórico acumulado, com `decision_source: account_untrust`.

A resposta contém, por exemplo:

```json
{
  "risk_score": 0,
  "decision_source": "account_untrust",
  "account_untrust": {
    "label": "Desconfiança acumulada da conta",
    "score": 80,
    "increment": 0,
    "risk_events": 4,
    "action": "two_factor_required",
    "window_hours": 24
  },
  "bank_notification": {
    "required": true,
    "status": "indicated_only",
    "reason": "account_untrust_threshold",
    "threshold": 60,
    "threshold_crossed": false
  }
}
```

`required` informa a condição atual; `threshold_crossed` identifica o primeiro
cruzamento nesta análise. `indicated_only` significa somente indicação na API:
nenhum aviso externo foi entregue. GET e repetição do ID retornam a mesma fotografia.
Os detalhes incluem score anterior, regras elegíveis, supressão de incremento e
parâmetros da política. [Resposta completa real da demonstração](../examples/untrust-response.json).

## Dados históricos usados para decidir o padrão (v7)

A avaliação reproduz o motor sobre o gerador sintético já existente no projeto:
150 cenários de validação e 200 de teste, com contas e datas separadas entre grupos.
As categorias incluem operações normais, comerciantes, famílias compartilhando
aparelhos, redes de aparelhos e concentração em destinatários.

Comparamos duas execuções independentes por cenário: sem acumulado e com acumulado.
O GNN fica desligado em ambas para não confundir os efeitos. A chegada simulada
segue a ordem cronológica dos eventos. Os rótulos vêm do gerador, não das regras.

| Efeito adicional sobre a decisão final do cenário | Validação (150) | Teste (200) |
|---|---:|---:|
| Rejeições de casos legítimos, com bloqueio acumulado ativado | 3 | 4 |
| Rejeições de fraude sintética, com bloqueio acumulado ativado | 0 | 0 |
| Rejeições de casos legítimos, no padrão somente 2FA | 0 | 0 |
| Novos desafios 2FA em casos legítimos, no padrão | 3 | 1 |
| Indicações de aviso ao banco, no padrão | 24 | 21 |

Estes números são da v7, anteriores à separação e ao Cofre da v8; não são métricas da política atual.
Números recalculados na v7 com duplicidade e ordem de chegada reproduzidas no
simulador. O relatório inclui transições por rótulo e exemplos com o motivo de
cada mudança; o experimento inicial permanece preservado em arquivo separado.

O bloqueio acrescentou rejeições indevidas sem ganho de rejeição de fraude nessa
amostra. Por esse resultado, ficou desativado por padrão. Os limiares 40/60/80,
a janela e a conversão de pontos são hipóteses configuráveis, não valores
regulamentares nem parâmetros estatisticamente calibrados em Pix real.

As duas amostras foram inspecionadas durante o desenvolvimento; a segunda não é
um teste final intocado. O gerador é pequeno e usa hipóteses artificiais. Esses
números não estimam a taxa de fraude ou de falsos positivos em produção.
O padrão de 2FA também não demonstrou ganho de detecção: é um controle de cautela,
com fricção mensurada nesta amostra, que exige validação antes do uso real.

Métricas: [comparação final](../models/untrust-synthetic-v1.metrics.json) e
[experimento inicial de bloqueio](../models/untrust-initial-blocking.metrics.json).

```powershell
docker compose --profile test run --rm --no-deps tests python -m scripts.evaluate_untrust
docker compose --profile test run --rm --no-deps tests python scripts/demo_untrust.py --url http://api:8000
```

Para implantação real: resultados confirmados de 2FA, liquidação e fraude;
revisão humana; medição de perdas e fricção; avaliação temporal nova e calibração
por segmento. Não se deve classificar clientes como fraudulentos a partir deste indicador.

## Instalação e parâmetros

Novas bases já incluem a coluna e o índice no SQL inicial. Bases existentes:

```powershell
Get-Content -Raw database/migrations/004_account_untrust.sql | docker compose exec -T db psql -U pix -d pix -v ON_ERROR_STOP=1
docker compose up --build -d --wait api
```

A migração é aditiva. Decisões antigas não recebem incrementos retroativos.
Os parâmetros ficam no objeto `untrust` de `config/risk-policy.json`, incluindo
`enabled`, `rejection_enabled`, janela, limiares, teto por evento, divisor e mínimo
de eventos para bloqueio. Configuração inválida impede a inicialização.

## Referências

A [pesquisa sobre agregação de atributos em transações](https://link.springer.com/article/10.1007/s10115-022-01653-0)
fundamenta usar contexto histórico por entidade. Isso não fornece nossos pesos.
As [regras de risco da Adyen](https://docs.adyen.com/point-of-sale/risk-management-pos)
mostram a utilidade de janelas e a necessidade de ajustar sinais de compartilhamento
ao contexto, evitando rejeições indevidas.
O [Stripe Radar](https://docs.stripe.com/radar/risk-evaluation) distingue níveis de
risco e revisão; seus modelos e limiares não foram copiados.
