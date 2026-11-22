# harness

Este repositório mantém skills e subagentes do **Devin CLI** para o fluxo de spec, implementação, revisão e fechamento de mudanças em pipelines de dados, adaptados de [felipeam86/pipe-skills](https://github.com/felipeam86/pipe-skills). As skills ficam em `skills/<nome>/SKILL.md`, os subagentes em `agents/<nome>.md` e o benchmark em `bench/`. Não é um plugin: quem usa copia `skills/` e `agents/` para `.devin/` do projeto ou para a pasta global do Devin.

Planejamento, edição e validação ficam na sessão principal. O agente `explorer` faz leituras extensas e delimitadas de código e dados; o `researcher`, as buscas de literatura da skill `research`; a skill `review` roda no subagente `reviewer`, que fixa um modelo de outro fornecedor e só lê. Não crie uma cadeia de subagentes para implementar os passos de um spec.

## Como trabalhar

- Leia a skill e os casos do benchmark que a exercitam antes de mudar seu comportamento. Preserve os nomes e o formato do Devin CLI: frontmatter de skill (`name`, `description`, `argument-hint`, `model`, `subagent`, `agent`, `allowed-tools`, `permissions`, `triggers`) e de subagente (`name`, `description`, `model`, `allowed-tools`, `max-nesting`), conforme [docs.devin.ai/cli](https://docs.devin.ai/cli/extensibility/skills/creating-skills). Campos só do Claude Code (`context: fork`, `disable-model-invocation`) não entram.
- Faça a menor mudança que resolve o pedido. Não amplie uma regra por causa de um exemplo isolado nem acrescente instruções só para aumentar uma nota estática.
- Nomes de skills, subagentes, chamadas (`/pipe:...`) e chaves de frontmatter em inglês; todo o texto das skills, perfis de agentes e documentação em português (pt-BR); tudo em Markdown comum. Regras duráveis ficam neste arquivo; diagnósticos, resultados e pendências ficam em `docs/`.
- Consulte a documentação atual de ferramentas e bibliotecas pelo Context7 antes de integrar ou alterar seu uso. Confira os comandos no `--help` da versão instalada.
- Use fixtures sintéticas e ambientes isolados nas avaliações. Não use dados reais de clientes nem permita que os testes alterem produção.

## Como testar as skills

O método segue o ciclo da [skill-creator do Claude](https://github.com/anthropics/skills/tree/main/skills/skill-creator): preparar casos reais, executar, avaliar, revisar os artefatos e melhorar a skill. O [NVIDIA SkillEvaluator](https://github.com/NVIDIA/SkillEvaluator) fornece checagens estáticas e comparação comportamental com e sem skill. Uma nota estática não demonstra que a skill melhora o resultado.

### Casos e critérios

- Ao criar uma skill ou mudar seu comportamento, prepare casos que exercitem a mudança e os comportamentos que precisam ser preservados. Inclua falhas relevantes e casos próximos que não devem ativar a skill quando alterar a descrição ou o escopo.
- Defina antes da execução o resultado esperado e critérios observáveis: arquivos produzidos, comandos executados, valores corretos, achados e ações que não podem ocorrer. Não avalie apenas a presença de palavras na resposta.
- Versione prompts, fixtures sintéticas, gabaritos, critérios e scripts em `bench/`, fora das pastas das skills, para que quem copia `skills/` não leve o benchmark. Para o Tier 3 do SkillEvaluator, use o contrato de `evals/evals.json` da versão utilizada.
- Um caso deve ser reproduzível em outro checkout. Prepare os repositórios, branches e dados de teste por fixture ou script; não dependa de caminhos absolutos da máquina do autor.
- O agente avaliado recebe o pedido e os insumos necessários, sem o gabarito, os graders ou conclusões de execuções anteriores.

### Verificações estáticas

Execute na raiz do repositório, substituindo `review` pela skill alterada:

```powershell
skillevaluator --version
skillevaluator quality-check ./skills/review
skillevaluator harness-check ./skills/review
skillevaluator tier1 ./skills/review --no-llm --output-dir ./reports/review
skillevaluator tier3 validate ./skills/review
```

`quality-check` verifica qualidade textual; `harness-check`, compatibilidade de carregamento pelo agente; Tier 1 acrescenta validações e scanners. Instale os scanners exigidos pela versão utilizada. Falha, dependência ausente, etapa ignorada ou resultado `INCOMPLETE` deve ser reportado como tal, sem contar como aprovação.

### Avaliação comportamental

- Execute cada caso em ambientes limpos e equivalentes, com a skill candidata e sem ela. Preserve o mesmo modelo, agente, prompt, fixtures, ferramentas e limites entre os dois grupos. Garanta que o grupo sem skill não carregue a candidata por outro caminho.
- Para comparar revisões, guarde a versão anterior e execute os mesmos casos com ambas. Registre a referência de cada versão; não compare resultados de cenários diferentes como se medissem a mesma mudança.
- Use o Tier 3 com backend preparado, credenciais pelo ambiente e dataset revisado. Exemplo para Claude Code em Docker:

```powershell
skillevaluator doctor --env-mode docker
skillevaluator tier3 evaluate ./skills/review --agents claude-code --env-mode docker --n-attempts 3 --no-stop-on-pass --results-dir ./reports/review/iteration-1
```

- A execução padrão compara com e sem skill. Não use `--skip-baseline` ao afirmar ganho. Fixe e registre o modelo e a configuração; as tentativas repetidas ajudam a distinguir melhoria de variação do modelo.
- Verifique critérios determinísticos com código. Nos demais, use julgamento com evidências do trace e dos artefatos. Leia também os resultados qualitativos: uma média pode esconder uma falha crítica.
- Guarde relatórios, traces e saídas por iteração fora dos arquivos da skill. Registre versão do avaliador, referência da skill, casos, configuração, critérios aprovados/reprovados e tempo, tokens ou custo quando efetivamente medidos. Não invente métricas ausentes.
- Corrija a skill a partir das falhas observadas e repita os casos afetados e os de regressão. Não afrouxe critérios para fazer uma revisão passar. Casos sem poder de distinguir comportamentos devem ser revistos de forma explícita.
- Antes de declarar a mudança validada, confira os artefatos, os critérios críticos e as regressões. Declare o alcance da evidência e tudo que não foi executado; não atribua ganho à skill sem comparação que o sustente.

## Referências

- [Dataset e fixtures do SkillEvaluator](https://docs.nvidia.com/skills/skillevaluator/eval-datasets)
- [Avaliação comportamental](https://docs.nvidia.com/skills/skillevaluator/tier3-live-evaluation)
- [Referência da CLI](https://docs.nvidia.com/skills/skillevaluator/cli-reference)
- [Decisões e motivos](docs/decisoes.md)
- [Experimentos e resultados](docs/experimentos.md)
