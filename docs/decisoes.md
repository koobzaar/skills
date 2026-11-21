# Decisões e motivos

Cada decisão abaixo traz o motivo e a fonte. Quando a fonte é um experimento deste repositório, o número vem de [experimentos.md](experimentos.md) e dos dados em [`docs/data/`](data/). Sem experimento, a decisão está marcada como julgamento.

## Origem

As skills partem de [felipeam86/pipe-skills](https://github.com/felipeam86/pipe-skills) (MIT, © 2026 Felipe Aguirre), apresentado no encontro da comunidade Claude no Nubank. O upstream roda como plugin do Claude Code e rastreia o trabalho em GitHub Issues ou Linear. Este repositório adapta o fluxo `spec → implement → review → close-spec` para o Devin CLI e para um time que usa um repositório git bare, sem GitHub.

## Alvo: Devin CLI, sem plugin

| Decisão | Motivo | Fonte |
| --- | --- | --- |
| Skills em `skills/<nome>/SKILL.md` e subagentes em `agents/<nome>.md`, copiados para `.devin/` do projeto ou para a pasta global do Devin | É assim que o Devin CLI descobre skills e subagentes. Sem plugin, os comandos ficam `/spec`, `/implement`, `/review` e `/close-spec`, sem prefixo. | [Skills](https://docs.devin.ai/cli/extensibility/skills/overview), [Subagents](https://docs.devin.ai/cli/subagents), [estrutura `.devin/`](https://docs.devin.ai/cli/extensibility) |
| `review` declara `agent: reviewer`, e `agents/reviewer.md` fixa `model:` num modelo de outro fornecedor | No Devin, uma skill com `agent:` roda como aquele subagente, e o `model:` do perfil escolhe o modelo. Assim o revisor muda de fornecedor sem script externo. | [Creating skills](https://docs.devin.ai/cli/extensibility/skills/creating-skills), [Subagents](https://docs.devin.ai/cli/subagents) |
| `reviewer` e `explorer` com `allowed-tools: [read, grep, glob, exec]` | No subagente, `allowed-tools` restringe as ferramentas (na skill, só aprova automaticamente). O revisor roda checagens mas não edita. | [Subagents](https://docs.devin.ai/cli/subagents) |
| `implement` e `close-spec` com `triggers: [user]` | Merge e escrita de código não devem começar sem o usuário pedir. | Julgamento |
| Nada de campos só do Claude Code (`context: fork`, `disable-model-invocation`) | O Devin ignora esses campos; mantê-los sugere um comportamento que não existe. | Julgamento, conferido com SkillEvaluator `harness-check` |

### Uso no Claude Code

O Claude Code só roda modelos Claude em subagentes. Para usar estas skills nele, é preciso trocar o `agent: reviewer` por `context: fork` com um revisor Opus (perde a revisão de outro fornecedor) ou chamar o Codex CLI pelo terminal dentro da skill `review` (`codex exec -m <modelo> --sandbox read-only`). O experimento B usou a primeira adaptação para medir as skills no Claude Code.

## Fluxo

| Decisão | Motivo | Fonte |
| --- | --- | --- |
| `implement` planeja, edita e valida na sessão principal; sem implementadores delegados | A troca entre implementadores perde o contexto das decisões. A Anthropic recomenda manter edição e decisão no modelo principal e usar subagentes menores para leituras delimitadas. | [Which Claude model](https://claude.dev/blog/which-claude-model-should-you-build-with/#mixing-models); [Fold subagents into the main loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop) |
| Um `explorer` para código e dados | Os dois exploradores tinham o mesmo papel (ler sem alterar, devolver resumo verificável). As regras de dados viraram uma seção. | Julgamento |
| Critérios de aceite com checagem executável, revisão por SHA fixado, critério aprovado como referência | O revisor e o modelo erram; a checagem executável não. A revisão vale para os SHAs que julgou. | [Code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/); [Verification](https://claude.dev/blog/how-the-claude-code-team-thinks-about-verification/) |
| `close-spec` confere SHA antes do squash e não faz push | O veredito vale para o que foi revisado. O remoto do time é um git bare: push é decisão humana. | Experimento B (caso `close-divergente`) |
| Removidas `preparar-repo`, `estado-final` e `promover-regra` | O modelo escreve o `AGENTS.md` do projeto e o `/init` já existe; as outras duas repetiam skills globais (`final-state`, `promote-rule`). | Decisão do usuário |

## Revisor

| Decisão | Motivo | Fonte |
| --- | --- | --- |
| Revisor de outro fornecedor | Quem escreve o código é Opus; um revisor de outra família erra em lugares diferentes. | [Code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/); experimento A |
| Modelo do revisor | Ver [experimentos.md](experimentos.md#experimento-a). | Experimento A; [Artificial Analysis](https://artificialanalysis.ai/models) |
| Sem persona ("você é um revisor sênior") | Personas de especialista não melhoraram a acurácia em nenhum modelo testado pela Wharton GAIL; um preprint da USC mediu queda em tarefas de conhecimento. A skill descreve a tarefa, quem lê o relatório e o critério de cada achado. | [Wharton GAIL, dez/2025](https://gail.wharton.upenn.edu/research-and-insights/playing-pretend-expert-personas/); [USC, arXiv 2603.18507](https://www.theregister.com/software/2026/03/24/telling-an-ai-model-that-its-an-expert-makes-it-worse/5226049) |
| O prompt diz que roda sem interação, pede premissas explícitas e relatório autossuficiente, e nomeia o modelo no relatório | São as recomendações dos guias de prompting da OpenAI e do Google para execuções sem usuário. O modelo é nomeado no perfil do subagente, porque é ele que fixa o modelo. | [OpenAI GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model/gpt-6.2-astra); [Google prompting strategies](https://aistudio.google.com/docs/prompting-strategies) |

## Tracker

O upstream tem `trackers/github.md` (GitHub Issues + Projects pelo `gh`) e `trackers/linear.md` (MCP do Linear). Não há opção local: as duas pedem um serviço externo, e as skills do upstream (`prd`, `assess`, `implement`) leem o tracker do `CLAUDE.md` do projeto.

No trabalho o remoto é um git bare, sem issues nem pull requests. O fluxo daqui já guarda o estado no próprio repositório: `specs/<slug>.md` é o trabalho aberto, `specs/done/` o fechado, `specs/pending.md` as pendências fora do escopo, e o commit de squash registra teste, risco, reversão e achados descartados. Um tracker de arquivos seria um terceiro lugar para manter em sincronia. Decisão: não portar os trackers. Se o time adotar Linear ou um forge, os dois arquivos do upstream podem ser trazidos sem mudança nas skills daqui, que não dependem de tracker.

## Idioma

Os nomes de skills, subagentes e chaves de frontmatter ficam em inglês; o texto das skills, os perfis e a documentação, em português. O experimento A comparou a skill `review` em inglês e em português no mesmo revisor; ver [experimentos.md](experimentos.md#idioma-da-skill).
