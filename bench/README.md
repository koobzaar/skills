# Benchmark

Scripts dos experimentos descritos em [docs/experimentos.md](../docs/experimentos.md). Os resultados resumidos ficam em [docs/data/](../docs/data/); os brutos (relatórios, transcrições) ficam fora do Git.

Requisitos: Python 3.13+, git, e os CLIs dos braços que você for rodar (`codex`, `agy`, `claude`), autenticados. O `matplotlib` entra via `uv run --with matplotlib`.

```sh
# 1. Fixtures sintéticas (repositórios git em bench/fixtures/)
py -I bench/build_fixtures.py bench/fixtures
py -I bench/build_fixtures2.py bench/fixtures
git clone -q bench/fixtures/join-duplica.bundle bench/fixtures/join-duplica
git -C bench/fixtures/join-duplica checkout -q -b main origin/main
git -C bench/fixtures/join-duplica checkout -q receita-com-regiao

# 2. Experimento A: revisores (cada execução recebe uma cópia limpa da fixture)
py -I bench/expA/run_expA.py bench/expA/results --attempts 2 --arms astra-max,neon-xhigh,opus-max
py -I bench/expA/grade_expA.py bench/expA/results sonnet
py -I bench/expA/grade_expA.py bench/expA/results sol

# 3. Experimento B: fluxo com e sem skill (Claude Code como agente substituto do Devin)
py -I bench/expB/run_expB.py bench/expB/results --attempts 2
py -I bench/expB/grade_expB.py bench/expB/results

# 4. Tabelas e gráficos
uv run --with matplotlib python -I bench/analyze.py bench docs
```

Não reconstrua as fixtures com execuções em andamento: os SHAs mudam e os gabaritos da segunda rodada deixam de valer.

`upstream/review/SKILL.md` é a skill `review` de [felipeam86/pipe-skills](https://github.com/felipeam86/pipe-skills) (MIT, © 2026 Felipe Aguirre), usada como braço de comparação.

Para refazer só os gráficos do README com os CSVs que já estão em `docs/data/`:

```sh
uv run --with matplotlib python -I bench/plot_readme.py
```

## Regressões de SHA

Use cópias descartáveis das fixtures e registre o estado antes e depois de cada caso. As cópias do experimento A agora começam na branch a revisar. Mantenha resultados das rodadas anteriores em outro diretório, com a referência da versão e a configuração que os produziu.

| Caso | Variante | Resultado esperado |
| --- | --- | --- |
| `segunda-rodada` | Forneça os dois SHAs anteriores com `main` no mesmo commit. | Pode partir do delta e deve detectar o status vazio e o teste enfraquecido, sem repetir o achado descartado ainda válido. |
| `segunda-rodada` | Avance `main` com um commit vazio e mantenha o SHA anterior do alvo nas entradas. | Inspeciona o diff completo desde a base e reporta o novo SHA do alvo. |
| `teste-equivalente` | Rode com a branch correta e repita alterando localmente o teste. | Na cópia limpa, pode executar e atribuir a checagem ao SHA revisado. Na cópia alterada, registra a checagem como não verificada e preserva a alteração local. |
| `close-feliz` | Acrescente um commit à branch de trabalho entre o squash e a limpeza. | O commit de squash contém a mudança revisada, com arquivamento e pendências. A branch e a worktree com o commit novo continuam presentes. |

Para verificar a retomada em novas rodadas do experimento B:

| Caso | Variante | Resultado esperado |
| --- | --- | --- |
| `implement-liquida` | Deixe o spec aprovado como arquivo não rastreado no checkout inicial. | O primeiro commit da branch contém o texto aprovado. O arquivo no checkout inicial é preservado. |
| `implement-liquida` | O caminho da worktree contém outro trabalho. | O agente preserva o diretório e relata a falha ou identifica uma worktree separada para o spec. |
| `close-feliz` | Interrompa depois do commit e antes da limpeza. | A retomada verifica o commit e o arquivamento, sem criar um segundo commit no alvo. |

## Skill `research`

Os casos, o gabarito e as queries do corpus estão em [research/cases.json](research/cases.json). O agente roda pelo Codex CLI com a rede do sandbox e a busca web nativa desligadas; o `lit.py` lê um corpus local (`LIT_CORPUS`), então a rodada não depende do limite da API. O corpus é gerado a partir de `research/corpus_ids.txt` e fica fora do Git.

```sh
# Testes do lit.py (sem rede)
py -I -B -m unittest discover -s bench/research -p "test_*.py"

# Corpus local: refaz a partir dos IDs versionados (OpenAlex e Semantic Scholar; S2_API_KEY ou SEMANTIC_API_KEY opcional)
py -I -B bench/research/build_corpus.py

# Casos com e sem a skill e acionamento, sequenciais
py -I -B bench/research/run_research.py bench/research/results/iter1 --cases ja-feito,premissa-contradita,citacao-falsa,confirmacao-trabalho --arms with,without
py -I -B bench/research/run_research.py bench/research/results/iter1 --triggers positivo-novidade,negativo-explicar,negativo-resumir,negativo-spec,negativo-dados
py -I -B bench/research/grade_research.py bench/research/results/iter1 [--original] [--csv docs/data/research_runs.csv]

# Passo de revisão: o perfil do reviewer no Antigravity deve marcar só a evidência E2
py -I -B bench/research/reviewer/run_reviewer.py bench/research/results/reviewer
```

`--original` corrige pelo gabarito anterior à revisão 1 (veja `_revisao_1` em `cases.json`). Uma execução com busca web nativa reprova no critério `isolamento`.
