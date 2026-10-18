# Desconfiança acumulada por conta (`account_untrust`)

Implementação atual: `pix-score-v9`. O indicador usa análises locais recentes para
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

A elegibilidade segue os códigos das regras, independentemente do grupo
configurado. Mover primeiro Pix, histórico insuficiente ou duplicidade para outro
grupo não cria suspeita; mover desvio de perfil não remove sua elegibilidade.
Os pontos continuam respeitando pesos e tetos. Veja a
[revisão com testes de casos parecidos](decision-contrasts.md).

Somente incrementos com `evidence_version=sender-evidence-v2` entram nas
consultas de acumulado, titular e grafo temporal. O legado continua auditável,
mas não transporta contribuições ambíguas de destinatário para a suspeita própria.
Novas análises gravam essa versão de evidência. O [Cofre contextual](contextual-trust.md)
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

A resposta pública contém apenas o resumo, por exemplo com `include_details=true`:

```json
{
  "key": "b3f1c2e0-7d4a-4c1e-9a52-1f0e6c9d2a77",
  "status": "two_factor_required",
  "metadata": {
    "risk_score": 0,
    "bank_notification_required": true,
    "rules": ["Desconfiança acumulada da conta"]
  }
}
```

`bank_notification_required` informa a necessidade de aviso; nenhum aviso externo
foi entregue. `untrust_score` pertence ao grafo, separado do acumulado da conta.
GET e repetição do ID usam a mesma decisão salva. `include_details=true` acrescenta
somente os nomes das regras aplicadas. Score anterior, regras elegíveis, supressão
de incremento e política permanecem na auditoria interna.

## Verificação atual

[test_account_untrust.py](../tests/test_account_untrust.py) verifica incrementos,
limiares, bloqueio optativo, supressão e uso do relógio do servidor.
[test_account_untrust_db.py](../tests/test_account_untrust_db.py) verifica expiração
e persistência. [Contrastes](decision-contrasts.md) e replay diferencial com
PostgreSQL verificam a separação entre score, referência e evidência própria.

O avaliador `scripts.evaluate_untrust` usa a política carregada do código atual,
comparando acumulado desligado, padrão 2FA e bloqueio optativo. Para gerar um
relatório novo sem substituir artefatos da aplicação:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
docker compose --profile test run --rm --no-deps -v "${PWD}/tmp:/results" tests python -m scripts.evaluate_untrust --output /results/untrust.metrics.json
```

Esse replay simula recepção em ordem cronológica, sem GNN, e não estima eficácia
real. Mudanças na decisão podem alterar aprovações disponíveis para perfis futuros.

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
