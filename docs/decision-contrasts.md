# Casos parecidos, decisões diferentes

Política atual `pix-score-v9`. Os contrastes isolam a causa da intervenção;
cenários têm histórico controlado, sem inferir intenção criminosa.

| Contexto comparado | Resultado com os padrões atuais |
|---|---|
| Primeiro Pix de R$ 499,99 / R$ 500, contas antigas | Aprovação / 2FA por ausência de referência. |
| Mesmo Pix de R$ 500, média aprovada de R$ 200 / R$ 100 | Score 0 / perfil 80 e 2FA. |
| Aparelho novo sozinho / junto de destinatário desconhecido, com amostra e valor elegíveis | Score 20 e aprovação / score 35 e 2FA. |
| Mesmo aparelho com dois / três titulares | Sem compartilhamento / 30 e 2FA. |
| Perfil 80 isolado / perfil 80 + origem recente 15 | 2FA / rejeição por dois fatores. |
| Pix limpo com acumulado 39 / 40 | Aprovação / 2FA, ambos com score transacional 0. |
| Mesmas contas/valor a 120s / 120s + 1 microssegundo | Duplicidade elegível / fora da janela. |
| Incremento a 24h − 1 microssegundo / exatamente 24h | Ainda ativo / expirado. |
| Três sinais de aparelho somando 70 brutos | Teto 40; incremento próprio 10, se não houver outra contribuição elegível. |
| GNN em `shadow` / `contribute`, score ≥75,0977 e artefatos válidos | Observa / pode elevar aprovação a 2FA, sem alterar score ou incremento próprio. |

As linhas pressupõem ausência de outros controles. Confiança contextual elegível
pode zerar o desvio de perfil; intervenções anteriores nunca são relaxadas pelo grafo.
Um novo ID enviado de fato à API acrescenta uma tentativa ao histórico e pode
acionar duplicidade; invariância de ID nos testes usa um contexto fixo.

## Elegibilidade própria

Os códigos de frequência, montante, perfil e três regras de aparelho são elegíveis.
Remapear o grupo de uma regra não muda sua natureza. Destinatário, ausência de
referência, idade, horário, duplicidade, vínculos e GNN não geram incremento próprio.
Uma restrição já ativa não é uma evidência nova.

## Verificação e replay

[test_untrust_contrasts.py](../tests/test_untrust_contrasts.py) cobre invariâncias,
tetos, remapeamento de fatores e separação de GNN/acumulado.
[test_untrust_replay.py](../tests/test_untrust_replay.py) compara o replay offline
com controlador e PostgreSQL reais, inclusive decisão, regras, perfil, incremento,
aviso e política, sob relógio controlado. Os testes de contribuição verificam
também históricos inteiros com o GNN habilitado.

```powershell
docker compose --profile test run --rm --no-deps tests pytest -q tests/test_untrust_contrasts.py tests/test_untrust_replay.py tests/test_gnn_contribution.py
```

Use o [ambiente isolado de testes](testes-politicas.md#execução). O simulador reproduz tentativas,
duplicidade, ordem de chegada e idempotência; não confirma liquidação nem sucesso
de 2FA. Os contrastes verificam implementação, sem estimar eficácia real.
