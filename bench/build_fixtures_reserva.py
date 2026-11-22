"""Lote reservado do experimento A. Uso: py -I build_fixtures_reserva.py <dir-saida>  (reaproveita helpers do lote 1)

Outro domínio (clientes ativos numa janela de datas, para o CRM), outra regra de negócio e outro tipo de defeito que os
casos de desenvolvimento, que giram em torno da receita por segmento. Não rode este lote enquanto estiver ajustando uma
skill: ele mede a versão candidata congelada. Gabarito em expA/cases_reserva.json."""
import json, pathlib, sys
sys.argv = [sys.argv[0], sys.argv[1]]
src = pathlib.Path(__file__).with_name("build_fixtures.py").read_text(encoding="utf-8")
helpers = src.split("# ---------- 1. revisar")[0]
exec(helpers)  # define OUT, sh, write, commit, new_repo e SHAS

AGENTS_CRM = """
# Clientes ativos

A contagem de clientes ativos vai para o painel do CRM, que escolhe com ela quem recebe campanha de retenção.

## Verificação
- Testes: `py tests/test_ativos.py`

## Regras
- Python puro, sem pandas. Datas em ISO 8601 (`AAAA-MM-DD`).
- A janela de N dias é aberta no início e fechada na data de referência: `(referencia - N dias, referencia]`. Todas as
  contagens usam a mesma janela, para os números do painel baterem entre si.
- Toda transformação devolve quantas linhas descartou e por quê.

## Revisão
- Bloqueia: contagem que diverge de `ativos` na mesma janela, ou linha descartada sem contagem.
"""

ATIVOS = """
import csv
from datetime import date, timedelta


def ler(caminho):
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ativos(compras, referencia, dias=30):
    \"\"\"Clientes com compra em (referencia - dias, referencia]. Devolve (clientes, descartes).\"\"\"
    inicio = referencia - timedelta(days=dias)
    vistos, invalidas = set(), 0
    for c in compras:
        try:
            d = date.fromisoformat(c["data"])
        except ValueError:
            invalidas += 1
            continue
        if inicio < d <= referencia:
            vistos.add(c["cliente_id"])
    return vistos, {"data_invalida": invalidas}
"""

# Referência 2026-03-31, 30 dias: janela (2026-03-01, 2026-03-31].
# loja: clientes 1 e 2 -> 2. site: cliente 3 -> 1 (o 4 cai no limite excluído, o 5 antes, o 7 depois). Uma data inválida.
COMPRAS = """
cliente_id,canal,data
1,loja,2026-03-15
1,loja,2026-03-20
2,loja,2026-03-31
3,site,2026-03-10
4,site,2026-03-01
5,site,2026-02-20
6,loja,data-ruim
7,site,2026-04-01
"""

TEST_ATIVOS = """
import sys, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pipeline.ativos import ler, ativos

if __name__ == "__main__":
    v, d = ativos(ler("dados/compras.csv"), date(2026, 3, 31))
    assert v == {"1", "2", "3"}, v
    assert d == {"data_invalida": 1}, d
    print(sorted(v), d)
"""

SPEC = """
# Ativos por canal

## Risco
Médio. O CRM escolhe por canal quem recebe campanha; um canal inflado manda campanha para quem já saiu.

## Objetivo
Contar clientes ativos por canal (`loja`, `site`) na mesma janela de `ativos`.

## Fora do escopo
Refatorar `ativos` ou mudar a regra de datas inválidas.

## Decisões
- Função nova `ativos_por_canal(compras, referencia, dias=30)` em `pipeline/ativos.py`, que devolve
  `({canal: clientes distintos}, descartes)`.

## Critérios de aceite
1. Na amostra `dados/`, com referência 2026-03-31, `ativos_por_canal` devolve `({'loja': 2, 'site': 1}, {'data_invalida': 1})`
   (conta à mão: o cliente 4 comprou em 2026-03-01, fora da janela). Checagem: `py tests/test_por_canal.py`.
2. A soma por canal bate com `ativos` quando cada cliente compra num só canal. Checagem: a mesma.
3. `ativos` não muda. Checagem: `py tests/test_ativos.py`.

## Passos
1. Criar `ativos_por_canal` e `tests/test_por_canal.py`.

## Pontos abertos
Nenhum.
"""

POR_CANAL = """


def ativos_por_canal(compras, referencia, dias=30):
    \"\"\"Clientes ativos distintos por canal, na janela de `ativos`. Devolve ({canal: n}, descartes).\"\"\"
    inicio = referencia - timedelta(days=dias)
    por_canal, invalidas = {}, 0
    for c in compras:
        try:
            d = date.fromisoformat(c["data"])
        except ValueError:
            invalidas += 1
            continue
        if COND:
            por_canal.setdefault(c["canal"], set()).add(c["cliente_id"])
    return {k: len(v) for k, v in por_canal.items()}, {"data_invalida": invalidas}
"""

TEST_POR_CANAL = """
import sys, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pipeline.ativos import ler, ativos_por_canal

if __name__ == "__main__":
    v, d = ativos_por_canal(ler("dados/compras.csv"), date(2026, 3, 31))
    assert v == ESPERADO, v
    assert d == {"data_invalida": 1}, d
    print(v, d)
"""

BASE_CRM = {"AGENTS.md": AGENTS_CRM, "pipeline/__init__.py": "", "pipeline/ativos.py": ATIVOS,
            "dados/compras.csv": COMPRAS, "tests/test_ativos.py": TEST_ATIVOS, "specs/ativos-por-canal.md": SPEC}

# ---------- reserva 1: limite da janela incluído, teste ajustado ao número errado ----------
r = new_repo("reserva-janela-inclusiva")
base = commit(r, "base", BASE_CRM)
sh(r, "checkout", "-q", "-b", "ativos-por-canal")
head = commit(r, "ativos_por_canal\n\nValidado: py tests/test_por_canal.py -> {'loja': 2, 'site': 2} {'data_invalida': 1}", {
    "pipeline/ativos.py": ATIVOS + POR_CANAL.replace("COND", "inicio <= d <= referencia"),
    "tests/test_por_canal.py": TEST_POR_CANAL.replace("ESPERADO", "{'loja': 2, 'site': 2}")})
sh(r, "checkout", "-q", "main")
SHAS["reserva-janela-inclusiva"] = {"base": base, "head": head}

# ---------- reserva 2: limpo, com duplicação do laço como isca de estilo ----------
r = new_repo("reserva-limpo-laco-duplicado")
base = commit(r, "base", BASE_CRM)
sh(r, "checkout", "-q", "-b", "ativos-por-canal")
head = commit(r, "ativos_por_canal\n\nValidado: py tests/test_por_canal.py -> {'loja': 2, 'site': 1} {'data_invalida': 1}", {
    "pipeline/ativos.py": ATIVOS + POR_CANAL.replace("COND", "inicio < d <= referencia"),
    "tests/test_por_canal.py": TEST_POR_CANAL.replace("ESPERADO", "{'loja': 2, 'site': 1}")})
sh(r, "checkout", "-q", "main")
SHAS["reserva-limpo-laco-duplicado"] = {"base": base, "head": head}

(OUT / "shas_reserva.json").write_text(json.dumps(SHAS, indent=2), encoding="utf-8")
print(json.dumps(SHAS, indent=2))
