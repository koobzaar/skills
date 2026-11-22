# Benchmark

Scripts dos experimentos descritos em [docs/experimentos.md](../docs/experimentos.md). Os resultados resumidos ficam em [docs/data/](../docs/data/); os brutos (relatórios, transcrições) ficam fora do Git.

Requisitos: Python 3.13+, git, e os CLIs dos braços que você for rodar (`codex`, `agy`, `claude`), autenticados. O `matplotlib` entra via `uv run --with matplotlib`.

```sh
# 1. Fixtures sintéticas (repositórios git em bench/fixtures/)
py -I bench/build_fixtures.py bench/fixtures
py -I bench/build_fixtures2.py bench/fixtures
py -I bench/build_fixtures_reserva.py bench/fixtures   # lote reservado do experimento A
git clone -q bench/fixtures/join-duplica.bundle bench/fixtures/join-duplica
git -C bench/fixtures/join-duplica checkout -q -b main origin/main
git -C bench/fixtures/join-duplica checkout -q receita-com-regiao

# 2. Experimento A: revisores (cada execução recebe uma cópia limpa da fixture)
py -I bench/expA/run_expA.py bench/expA/results --attempts 2 --arms astra-max,neon-xhigh,opus-max
py -I bench/expA/grade_expA.py bench/expA/results sonnet
py -I bench/expA/grade_expA.py bench/expA/results sol
# Lote reservado: só com a versão candidata congelada, depois do lote de desenvolvimento
py -I bench/expA/run_expA.py bench/expA/results --set reserva --attempts 3 --arms astra-max,neon-xhigh

# 3. Experimento B: fluxo com e sem skill (Claude Code como agente substituto do Devin)
py -I bench/expB/run_expB.py bench/expB/results --attempts 2
py -I bench/expB/grade_expB.py bench/expB/results

# 4. Tabelas e gráficos
uv run --with matplotlib python -I bench/analyze.py bench docs
```

Testes dos graders, da agregação e do `conferir.py`, sem rede nem agentes:

```sh
py -I -B -m unittest discover -s bench -p "test_*.py"
```

As cópias de cada execução ficam em `<temp>/pipe-bench-runs/` (ou em `BENCH_RUNS`, que precisa estar fora do repositório), para o agente avaliado não alcançar o gabarito nem os graders. O `analyze.py` conta timeouts e falhas do CLI como erro, no denominador e no custo, e separa o lote reservado (`case_set`) do de desenvolvimento.

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
