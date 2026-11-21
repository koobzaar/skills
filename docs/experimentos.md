# Evidência do benchmark

## SkillEvaluator

A sessão anterior registrou estes resultados para as versões anteriores à revisão do fluxo de SHAs. As notas estáticas estão em [docs/data/skillevaluator.csv](data/skillevaluator.csv). O avaliador usado foi o NVIDIA SkillEvaluator 1.0.1.

| Skill | Quality check | Tier 1 sem juiz | Tier 1 com juiz |
| --- | ---: | --- | --- |
| `spec` | 83,5 | 9/9 | 9/10. Rubrica 72,7, com exemplos e simulação de acionamento abaixo do mínimo por critério |
| `implement` | 86,0 | 9/9 | 9/10. Rubrica 68,2, abaixo de 70, com exemplos abaixo do mínimo por critério |
| `review` | 86,0 | 9/9 | 9/10, incompleto. A rubrica passou com 82,7 |
| `close-spec` | 86,0 | 9/9 | Resultado ausente no histórico consultado |

A primeira rodada estática ficou em 8/9 por falta do Gitleaks. A sessão registrou 9/9 nas quatro skills após a instalação, com quatro verificações não aplicáveis por skill. A rubrica com juiz avalia o texto da skill. A execução comportamental ao vivo do Tier 3 ainda está pendente.

Na rodada estática após o ajuste dos SHAs, o `quality-check` mediu 86,5 em `spec`, 89,0 em `implement` e 87,25 em `review` e `close-spec`. O Tier 1 sem juiz ficou em 8/9 nas quatro skills. O Gitleaks passou e o SkillSpector ficou incompleto por falha ao adquirir o lock. O `harness-check` marcou carregamento em seis harnesses cobertos pelo avaliador, entre os quais o Devin CLI não consta. O `tier3 validate` apontou a ausência de `evals/` em cada pasta de skill. Os casos do projeto ficam em `bench/`.

### Reavaliação com juiz

O comando `skillevaluator rubric-eval ./skills/<nome> -r cli` usou NVIDIA Build com `nvidia/nemotron-3.5-lightning-30b-a3b`. Cada versão final passou nos nove critérios, com mínimo de 7/10 por critério e 70/100 na nota global.

| Skill | Primeira rodada | Versão final | Exemplos na versão final |
| --- | --- | --- | --- |
| `spec` | 79,5, aprovada | 78,2, aprovada | 7/10 |
| `implement` | 73,6, reprovada em exemplos | 83,6, aprovada | 8/10 |
| `review` | 76,8, aprovada | 77,3, aprovada | 8/10 |
| `close-spec` | 76,8, reprovada em exemplos | 77,7, aprovada | 8/10 |

Em `implement`, uma rodada intermediária obteve 76,8 com 6/10 em exemplos. A versão aprovada mostra cinco pedidos de implementação e três pedidos próximos que cabem em outras skills. Em `close-spec`, os exemplos cobrem squash bem-sucedido, alvo que avançou e alterações locais que impedem a limpeza. Os relatórios finais foram salvos localmente em `reports/nvidia-rubric-current/`. Esta rodada executou a rubrica isolada. O Tier 1 completo e a execução comportamental no Devin não foram repetidos.

### Busca por 90/100

A nota global usa pesos 3, 2 e 1 para critérios de importância alta, média e baixa. Descrição, clareza das instruções, exemplos, simulação de acionamento e completude do fluxo têm peso 3. Portanto, marcar 8/10 repetidamente nesses critérios mantém a nota perto de 80, mesmo com boa pontuação nos demais.

No melhor resultado de `review` (86,8), o juiz deu 9 aos outros seis critérios e 8 à clareza das instruções, à simulação de acionamento e ao tom. Esses três descontos explicam a diferença até 90 nessa rodada.

As revisões testaram entradas e saídas explícitas, exemplos com dados verificáveis, roteamento entre as quatro skills e retomada em caso de falha. A melhoria mais clara apareceu em `review` ao separar os modos branch e spec, declarar os insumos obrigatórios e ampliar os exemplos de veredito. Em `implement`, versões mais longas receberam notas menores em exemplos, tom ou acionamento. As avaliações que o juiz devolveu com identificadores de critérios inválidos ficam sem nota. O [CSV da rubrica](data/rubrica-nvidia.csv) preserva as rodadas, inclusive essas falhas.

| Skill | Referência | Nota usada na seleção | Confirmação da versão selecionada |
| --- | ---: | ---: | ---: |
| `spec` | 78,2 | 80,9 | 80,9 |
| `implement` | 83,6 | 83,6 | 83,6 |
| `review` | 77,3 | 86,8 | 76,8 |
| `close-spec` | 77,7 | 79,5 | 78,2 |

As quatro passaram na confirmação. Nenhuma atingiu 90. A variação de dez pontos em `review` impede tratar o 86,8 isolado como um ganho reproduzível. Os relatórios locais da confirmação estão em `reports/nvidia-rubric-selected/`. O `quality-check` estático passou nas quatro, com média 87,5. O Tier 1 completo e os ensaios no Devin ficaram fora desta rodada.

## Fechamento de spec

O grader do [experimento B](../bench/expB/grade_expB.py) registrou 12/12 com `close-spec` nas duas tentativas do cenário de squash bem-sucedido com Gemini 4 Neon via Antigravity. Sem skill, foram 9/12 e 10/12, com lacunas no registro de teste, risco ou reversão. No cenário com SHAs divergentes, ambos os braços marcaram 4/4 nas duas tentativas. O [CSV histórico](data/expB_runs.csv) inclui também o conjunto Claude Code e os demais cenários. São fixtures sintéticas com poucas tentativas.

## Revisor

O [resumo histórico do experimento A](data/expA_summary.csv) preserva 59 execuções com nota em oito braços de modelos, idiomas e versões da skill. O gráfico do README mostra Astra e Neon com a revisão do harness em português e a versão de origem em inglês. A proporção de problemas encontrados vem dos achados plantados em [seis casos](../bench/expA/cases.json). Tentativas indisponíveis deixam grupos com tamanhos diferentes e a amostra tem efeito teto no veredito. Compare os valores como descrição do recorte, sem extrapolar ganho para outros casos.

## Revisão dos SHAs

O texto anterior fixava os SHAs para ler o diff, mas a execução na worktree podia observar outro commit ou alterações locais. Também faltava transmitir o SHA anterior do alvo para justificar uma revisão incremental. A revisão desta iteração exige que a worktree corresponda ao commit julgado, transmite ambos os SHAs à rodada seguinte e usa o commit revisado como argumento do squash. Os [casos de regressão](../bench/README.md#regressões-de-sha) descrevem os resultados esperados.

Um teste local substituiu a chamada ao modelo por asserções no runner do experimento A. Confirmou que a cópia começa limpa na branch certa, que o prompt inclui os dois SHAs da rodada anterior e que, ao avançar a referência do alvo, o prompt conserva o SHA anterior. A fixture original continuou na branch alvo. A resposta das skills aos casos de regressão segue sem avaliação comportamental nesta iteração.
