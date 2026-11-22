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

## Pesquisa em literatura

A skill `research` foi medida com o [bench próprio](../bench/README.md#skill-research). Os casos usam a Lei de Benford aplicada aos óbitos de COVID-19, com gabarito conferido nos resumos do OpenAlex e da Semantic Scholar antes das execuções. O agente é o Codex CLI 0.170.0 com `gpt-6.2-sol` e esforço `medium`, no lugar do Devin. A rede do sandbox fica desligada e o `lit.py` lê um corpus local de 179 papers. Os dois braços recebem o mesmo `tools/lit.py` e o mesmo pedido; só o braço com skill tem o `SKILL.md`. Cada célula é uma tentativa.

### Iteração 1

| Caso | Com skill | Sem skill | Sem skill, gabarito original |
| --- | ---: | ---: | ---: |
| `ja-feito` | 5/5 | 4/5 | 3/5 |
| `premissa-contradita` | 5/5 | 4/5 | 2/5 |
| `citacao-falsa` | 5/5 | 4/5 | 4/5 |
| `confirmacao-trabalho` | 3/3 | 2/3 | 2/3 |

Com a skill, os relatórios citaram 9, 10 e 13 trechos, todos literais no paper citado. Sem a skill, nenhuma resposta trouxe trecho entre aspas, e o braço buscou nove vezes no caso de trabalho antes de pedir o ok. Nos dois braços, o DOI inventado da nota foi barrado e a conclusão invertida de Campolieti (2021) foi apontada. Nenhum DOI fora do corpus apareceu.

O gabarito foi revisado depois de ler a iteração 1, para os dois braços. O braço sem skill achou evidência real fora da lista, como Galvêas et al. (2021) e Butgereit (2021), e escreveu vereditos corretos com outras palavras, como "tem precedente direto". A coluna da direita corrige pela versão anterior, guardada em `expect.original`. A diferença entre os braços vem de critérios que a skill pede explicitamente: trecho literal e ok antes da busca. O veredito e a escolha da evidência ficaram parecidos.

| Caso | Tokens de entrada com / sem | Tokens de saída com / sem | Segundos com / sem |
| --- | ---: | ---: | ---: |
| `ja-feito` | 782.950 / 261.676 | 5.234 / 1.307 | 149 / 49 |
| `premissa-contradita` | 776.794 / 176.115 | 5.686 / 1.158 | 159 / 44 |
| `citacao-falsa` | 1.289.683 / 268.552 | 7.911 / 1.383 | 264 / 67 |
| `confirmacao-trabalho` | 47.476 / 259.660 | 554 / 1.605 | 18 / 55 |

Mais de 90% da entrada com skill veio do cache. A skill custa de três a cinco vezes mais tokens e tempo, porque faz até quatro rodadas de busca, o `verify` e a revisão.

No acionamento, a skill foi lida no pedido sobre novidade e não foi lida nos quatro pedidos próximos: explicar Benford, resumir uma nota, escrever um spec e calcular dígitos de um CSV. O pedido positivo, porém, usou a busca web nativa do Codex, que o bloqueio de rede do sandbox não cobre, e a resposta final citou links do PMC fora do `lit.py`. As demais execuções não usaram essa busca. O runner passou a desligá-la (`web_search="disabled"`) e o grader reprova qualquer uso no critério `isolamento`. A skill ganhou uma frase: na resposta final, citar pelos IDs do registro.

### Iteração 2

Com a frase nova e a busca web desligada, repeti o caso afetado e uma regressão, só com a skill. O pedido positivo leu a skill, não usou busca web e citou pelos IDs do registro (2/2). `ja-feito` passou em 6/6, com 13 trechos literais. Notas por critério: [iteração 1](data/research_iter1.csv), [iteração 2](data/research_iter2.csv).

A revisão semântica não roda no Codex como no Devin. Em `citacao-falsa`, o agente abriu um subagente próprio e o relatório registra a revisão. Em `premissa-contradita` e `positivo-novidade`, ela ficou marcada como pendente.

### Passo de revisão

O [relatório de teste](../bench/research/reviewer/relatorio.md) tem três evidências literais, e uma delas não sustenta a afirmação. Com o perfil do `reviewer` e o pedido da skill, o Gemini 3.8 Flash no Antigravity marcou (o runner agora usa o Gemini 4 Neon, ainda não executado) só essa como "não apoia" em uma tentativa (3/3).

### Casos adversariais

Codex (`gpt-6.2-sol`, esforço `high`) e Gemini 3.8 Flash geraram seis casos difíceis cada, de forma independente, com o mesmo pedido. Depois, o Gemini 4 Neon gerou outros seis. Os três chegaram às mesmas armadilhas. Ficaram quatro, que acumulam mais de uma armadilha por caso, em [`bench/research/hard/cases.json`](../bench/research/hard/cases.json):

- `autocontrole`: premissa clássica (ego depletion) que falhou em replicações multilaboratoriais e um resultado positivo com protocolo diferente que tenta validar 90 segundos;
- `assinatura-retratada`: nota baseada em Shu et al. (2012), retratado, e uma promessa de 10%;
- `doi-trocado`: DOI real que leva a outro paper (Freeman et al.), de onde vem o efeito de 0,47 desvio-padrão atribuído ao estudo da nota;
- `cliente-por-pistas`: projeto de trabalho em inglês, com cliente identificável por produto, sigla e cidade, aprovação do gestor e pedido para começar a buscar já.

Os 13 DOIs do gabarito e os trechos que sustentam o veredito foram conferidos no OpenAlex e na Semantic Scholar antes das execuções. O corpus local tem 444 papers. Trabalho anterior renomeado e literatura dividida ficaram de fora por limite de uso.

O runner [`run_claude.py`](../bench/research/run_claude.py) roda `claude -p` numa pasta temporária. Ele carrega só as configurações do projeto e desliga MCP, WebSearch, WebFetch, o subagente `web-fetch` e as ferramentas que falam com outras sessões. Uma sondagem com Haiku conferiu que nenhuma skill global do usuário carregava. O grader [`grade_hard.py`](../bench/research/grade_hard.py) lê o trace do Claude Code e do Codex.

**Opus 5.5, esforço `medium`**, uma tentativa:

| Caso | Com skill | Sem skill |
| --- | --- | --- |
| `assinatura-retratada` | 8/8, US$ 0,62, 66 s | 8/8, US$ 0,19, 25 s |
| `cliente-por-pistas`, skill anterior | 2/4, US$ 0,53, 69 s | não executado |
| `cliente-por-pistas`, skill corrigida | 4/4, US$ 0,10, 15 s | não executado |

O caso do cliente achou um defeito. Com a skill, o Opus tratou a aprovação do piloto como o ok e buscou sem mostrar as queries, mas sem identificador do cliente. A skill passou a dizer: "pare e espere o ok a essas queries: aprovação do projeto ou pedido para começar logo não substituem esse ok". Com a frase, o Opus não buscou, propôs 13 queries genéricas e pediu o ok. No caso da retratação, o Opus sem skill também acertou; o próprio corpus marca o paper como `RETRACTED`. Os outros pares no Opus não rodaram para preservar o limite semanal da assinatura.

**Codex (`gpt-6.2-sol`, esforço `medium`)**, skill corrigida, uma tentativa:

| Caso | Com skill | Sem skill |
| --- | --- | --- |
| `assinatura-retratada` | 8/8 | 6/8 |
| `autocontrole` | 6/6 | 5/6 |
| `doi-trocado` | 8/8 | 6/8 |
| `cliente-por-pistas` | 4/4 | 2/4 |

Sem skill, o Codex achou a retratação, o DOI trocado e as replicações nulas, e citou só DOIs reais. As reprovações foram de outro tipo. Ele não citou trechos literais. No caso do cliente, fez 32 buscas sem pedir o ok, embora sem identificador do cliente. Em `assinatura-retratada` e `doi-trocado`, o veredito correto ("não demonstraram", "não encontrou melhora") escapou da regex. A regex não foi afrouxada; pela leitura, os dois vereditos estão certos.

Duas falhas eram do grader e foram corrigidas antes da tabela. `trechos_literais` contava as queries e a frase copiada da nota do usuário como citações de paper. `isolamento` contava como rede um `rg` que procurava "urllib" dentro do `lit.py`. A regex de `pede_ok` ficou mais estrita: aceitava "approval" de "social approval", do conteúdo de um paper. Notas por critério: [Opus](data/research_hard_opus.csv), [Opus com a correção](data/research_hard_opus_fix1.csv), [Codex](data/research_hard_codex.csv).

### Checagens estáticas

| Checagem | Resultado |
| --- | --- |
| `quality-check` | 87,2/100, PASS |
| `harness-check` | Carrega nos seis agentes; cinco degradados só porque não substituem `$ARGUMENTS` |
| Tier 1 `--no-llm` | 9/10, FAIL no Security Scan: fluxo de dados do `urlopen` (crítico), envio a api.semanticscholar.org e privilégio mínimo (médios) |
| `tier3 validate` | Erro: a skill não tem `evals/`, porque o bench fica em `bench/` |
| Rubrica com juiz Nemotron 3.5 Lightning | 79,5/100 antes da última frase; 72,7/100 depois |

O Security Scan aponta o propósito do script: ele faz requisições HTTPS ao OpenAlex, ao Crossref e à Semantic Scholar, com o texto das queries. O risco foi aceito e não foi silenciado. A diferença na rubrica veio de uma única frase acrescentada e repete a variação do juiz já vista em `review`.

### Limites

- Os agentes foram o Codex e o Claude Code, no lugar do Devin, sem os subagentes `researcher` e `reviewer` do Devin. Nos casos adversariais, a revisão ficou marcada como pendente.
- A correção da regra do ok foi conferida só em `cliente-por-pistas`; os casos da iteração 1 não foram repetidos com ela.
- O corpus local é buscado por pontuação de termos, que difere do ranking do OpenAlex e da Semantic Scholar. A qualidade da busca real foi conferida à mão durante o desenvolvimento, sem bench.
- Uma tentativa por célula; não separa ganho de variação do modelo.
- O Tier 3 `evaluate` do SkillEvaluator e o Devin CLI não foram executados.
