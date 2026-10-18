# Pix Antifraude

8 slides de conteúdo: aproximadamente 6min40s. Perguntas: 3 minutos.

## 1. Pix Antifraude: estrutura do projeto (45s)

Somos Vinícius Guimarães Drexler e Wallace Dametto Teixeira. Construímos uma API de análise de risco de Pix com Python, FastAPI e PostgreSQL. Escolhemos uma estrutura parecida com a do primeiro desafio por seguir boas práticas de organização e facilitar a manutenção do código. Essa organização separa as responsabilidades e permite ajustar regras e evoluir o projeto com mais clareza.

## 2. Regras: pesquisa e implementação (60s)

Começamos pela pesquisa de práticas consolidadas de prevenção a fraude. As referências documentadas são Stripe Radar e Adyen, instituições de pagamentos, além das orientações do Banco Central. Essa pesquisa ajudou a separar sinais de risco, pontuação e ação. Implementamos 13 regras. Elas cobrem frequência e montante acumulado, primeiro Pix e ausência de histórico aprovado, idade das contas, destinatário desconhecido, desvio de valor, dispositivos, horário e possível duplicidade. Como exemplos, a sexta tentativa ou R$ 30 mil acumulados em dez minutos são limites fortes definidos pelo projeto. Um aparelho novo soma 20 pontos, conforme valor e histórico. Esses pesos e limites são escolhas do protótipo. O sistema bancário integrador ainda precisa aplicar os limites regulatórios efetivos da conta. A API não consulta esses limites nem comprova conformidade regulatória.

## 3. Risk score: soma ponderada dos sinais (55s)

Criamos o campo risk_score para reunir a contribuição das anormalidades encontradas. A soma é ponderada, tem tetos por fator e fica limitada a 100. Isso evita contar repetidamente sinais muito parecidos. Por exemplo, aparelho desconhecido soma 20 e destinatário desconhecido soma 15, totalizando 35 e solicitando autenticação adicional. A partir de 30 há 2FA. A partir de 80, a rejeição por score exige pelo menos dois fatores positivos. Um fator isolado de perfil, mesmo com 80 pontos, pede 2FA. Os limites fortes têm prioridade. A ausência de referência aprovada também exige 2FA a partir de R$ 500, independentemente dos pesos. A finalidade é reduzir intervenções indevidas sem deixar de tratar sinais combinados. O score é heurístico: 80 pontos não significa 80% de probabilidade de fraude.

## 4. Histórico: contexto para reduzir falsos positivos (50s)

A análise de histórico se tornou indispensável porque um sinal isolado pode representar uma situação legítima. Trocar de celular não significa fraude. O mesmo vale para um novo destinatário ou um pagamento alto que já é habitual naquela relação. Por isso usamos aprovações anteriores para construir o perfil de valores e reconhecer aparelhos e destinatários. Rejeições e pendências contam como tentativas, mas não elevam a referência de valores. A confiança contextual pode zerar somente o desvio de perfil quando há amostra suficiente e o valor é compatível com a relação. Ela exige cinco amostras do pagador, três da relação em dois dias distintos e valor entre 50% e 200% da mediana. Os demais controles continuam ativos. Também excluímos dados futuros e evitamos que um reenvio conte duas vezes.

## 5. Testes: regras, combinações e casos legítimos (45s)

Construímos a suíte com apoio de IA, incluindo casos positivos, negativos e combinações de regras. A proposta inicial tinha cerca de 400 testes. O projeto evoluiu e a documentação registra 691 casos aprovados na execução integrada com a contribuição da GNN ativa. Incluímos variações das 13 regras, limiares de decisão, histórico e situações legítimas que poderiam gerar alertas indevidos, como troca de aparelho e pagamentos habituais. A suíte também verifica concorrência, persistência, reenvios e a contribuição do grafo. Os testes da GNN confirmam que ela pode solicitar 2FA, sem somar pontos ao risk_score nem rejeitar sozinha. Essa cobertura verifica o comportamento do protótipo e não estima a taxa de erro em operações reais.

## 6. GNN: análise da rede de transações Pix (50s)

Além das regras, implementamos uma Graph Neural Network simplificada, inspirada em GraphSAGE. Ela analisa a rede relacional das transações, incluindo titulares e aparelhos, com direção e tempo dos eventos. O objetivo é investigar padrões como vários recebimentos seguidos de repasses rápidos. Duas camadas agregam informações dos vizinhos. O treinamento usa PyTorch e a inferência usa NumPy. A GNN já está integrada às decisões no modo contribute do protótipo. Se as demais camadas aprovarem a operação, uma avaliação completa com score do grafo a partir de 75,0977 pode exigir 2FA. O grafo não rejeita sozinho, não remove restrições anteriores e não soma pontos ao risk_score. O untrust_score representa sua saída separada, sem probabilidade calibrada de fraude.

## 7. Validação da GNN e controle de falsos positivos (60s)

A meta inicial da equipe era menos de 10% de falsos positivos. Na validação adotamos critérios mais rigorosos para propostas de 2FA adicional, incluindo limite superior nominal de 95% de até 1% para novos desafios em legítimos aprováveis e ganho nos positivos sintéticos. Ampliamos os casos legítimos difíceis e separamos treino, validação, calibração e teste. A calibração conservadora usou 900 cenários e o teste usou 1.800. Os três candidatos passaram nos critérios numéricos em duas propostas, com zero desafios indevidos entre 1.064 legítimos aprováveis por candidato. Com base nessa avaliação, a equipe habilitou a contribuição no protótipo, usando o candidato da semente 42 e o limiar congelado. A integração vincula modelo, corte e política aos artefatos avaliados. Os resultados são sintéticos e não garantem erro zero em operações reais.

## 8. Demonstração: decisão com justificativas (35s)

A demonstração apresenta decisões com score 0, 35 e 95. O caso normal recebe aprovação. Aparelho e destinatário desconhecidos somam 35 e exigem 2FA. Desvio de perfil e destinatário desconhecido somam 95 e levam à rejeição pelas regras. A GNN complementa essa análise: mesmo com risk_score zero, o grafo pode pedir 2FA quando seu sinal relacional alcança o corte e satisfaz as condições da integração. A resposta explica os motivos e o banco preserva as evidências. Repetir o mesmo ID e conteúdo mantém a decisão original. Agora abrimos para perguntas.

## 9. Perguntas (180s)

Reservar três minutos para perguntas, sem exibir o tempo no slide. Sobre a arquitetura, explicar a escolha de estrutura semelhante à do primeiro desafio e a facilidade de manutenção. Sobre a GNN, explicar que contribute é o padrão do protótipo: score relacional a partir de 75,0977 pode elevar aprovação para 2FA, sem rejeitar sozinho ou alterar o risk_score. O limiar fica vinculado ao modelo e à política avaliados. Sobre testes, a documentação registra 691 casos aprovados com contribuição ativa. Sobre os resultados, esclarecer que os cenários de validação são sintéticos. O motor solicita 2FA, mas não executa autenticação nem confirma liquidação.