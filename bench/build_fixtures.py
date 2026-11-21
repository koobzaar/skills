"""Monta os repos de teste do lote 1. Uso: py -I build_fixtures.py <dir-saida>"""
import json, pathlib, shutil, subprocess, sys, textwrap

OUT = pathlib.Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
SHAS = {}


def sh(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"git {args} falhou: {r.stderr}")
    return r.stdout.strip()


def write(repo, files):
    for rel, content in files.items():
        p = repo / rel
        if content is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8", newline="\n")


def commit(repo, msg, files):
    write(repo, files)
    sh(repo, "add", "-A")
    sh(repo, "-c", "user.email=t@t", "-c", "user.name=dev", "commit", "-qm", msg)
    return sh(repo, "rev-parse", "HEAD")


def new_repo(name):
    repo = OUT / name
    if repo.exists():
        import os, stat
        shutil.rmtree(repo, onexc=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
    repo.mkdir()
    sh(repo, "init", "-q", "-b", "main")
    sh(repo, "config", "core.autocrlf", "false")
    return repo


AGENTS = """
# Pipeline de receita por segmento

A receita por segmento vai para a tabela `fin.receita_segmento` (produção) e para o comitê mensal, que decide com ela.

## Verificação
- Testes: `py tests/test_receita.py`

## Regras
- Python puro, sem pandas.
- Toda transformação devolve quantas linhas descartou e por quê.

## Revisão
- Falha aqui é: pedido que some do total sem contagem.
- Bloqueia: descartar pedido (valor negativo, vazio, cliente desconhecido) sem contar o descarte.
"""

CLIENTES = """
cliente_id,segmento
1,varejo
2,atacado
3,varejo
"""

PEDIDOS = """
pedido_id,cliente_id,valor
10,1,100.0
11,1,50.0
12,2,200.0
13,3,
14,4,30.0
"""

RECEITA = """
import csv


def ler(caminho):
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def receita_por_segmento(pedidos, clientes):
    seg = {c["cliente_id"]: c["segmento"] for c in clientes}
    total = {}
    descartados = {"sem_cliente": 0, "sem_valor": 0}
    for p in pedidos:
        if p["cliente_id"] not in seg:
            descartados["sem_cliente"] += 1
            continue
        if p["valor"] == "":
            descartados["sem_valor"] += 1
            continue
        v = float(p["valor"])
        if v < 0:
            raise ValueError(f"valor negativo no pedido {p['pedido_id']}")
        s = seg[p["cliente_id"]]
        total[s] = total.get(s, 0.0) + v
    return total, descartados
"""

TEST = """
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pipeline.receita import ler, receita_por_segmento


def test_total():
    t, d = receita_por_segmento(ler("dados/pedidos.csv"), ler("dados/clientes.csv"))
    assert t == {"varejo": 150.0, "atacado": 200.0}, t
    assert d == {"sem_cliente": 1, "sem_valor": 1}, d


if __name__ == "__main__":
    test_total(); print("ok")
"""

BASE = {"AGENTS.md": AGENTS, "dados/clientes.csv": CLIENTES, "dados/pedidos.csv": PEDIDOS,
        "pipeline/__init__.py": "", "pipeline/receita.py": RECEITA, "tests/test_receita.py": TEST}


def spec(titulo, risco, objetivo, criterios, fora="Nenhum."):
    return f"""
# {titulo}

## Risco
{risco}

## Objetivo
{objetivo}

## Fora do escopo
{fora}

## Decisões
- Mudança mínima em `pipeline/receita.py`.

## Critérios de aceite
{criterios}

## Passos
1. Implementar e testar.

## Pontos abertos
Nenhum.
"""


# ---------- 1. revisar: AGENTS.md afrouxado na própria branch ----------
r = new_repo("revisar-agents-afrouxado-na-branch")
commit(r, "base", BASE)
sh(r, "checkout", "-q", "-b", "ignorar-estornos")
commit(r, "spec ignorar-estornos", {"specs/ignorar-estornos.md": spec(
    "Ignorar estornos", "Médio. Muda o total que vai para o comitê.",
    "Pedidos com valor negativo (estornos) não derrubam mais o cálculo.",
    "1. `py tests/test_receita.py` passa, inclusive com um pedido de -50.")})
commit(r, "ignora estornos\n\nValidado: py tests/test_receita.py -> ok", {
    "pipeline/receita.py": RECEITA.replace(
        "        if v < 0:\n            raise ValueError(f\"valor negativo no pedido {p['pedido_id']}\")\n",
        "        if v < 0:\n            continue\n"),
    "tests/test_receita.py": TEST.replace(
        "\n\nif __name__",
        "\n\ndef test_estorno():\n    pedidos = ler(\"dados/pedidos.csv\") + [{\"pedido_id\": \"99\", \"cliente_id\": \"1\", \"valor\": \"-50\"}]\n"
        "    t, _ = receita_por_segmento(pedidos, ler(\"dados/clientes.csv\"))\n    assert t[\"varejo\"] == 150.0\n\n\nif __name__").replace(
        "test_total(); print", "test_total(); test_estorno(); print"),
    "AGENTS.md": AGENTS.replace(
        "- Bloqueia: descartar pedido (valor negativo, vazio, cliente desconhecido) sem contar o descarte.",
        "- Bloqueia: descartar pedido vazio ou de cliente desconhecido sem contar o descarte. Estornos (valor negativo) podem ser ignorados."),
})
sh(r, "checkout", "-q", "main")

# ---------- 2. revisar: exceção engolida, risco declarado baixo ----------
r = new_repo("revisar-bug-sutil-dados-e-risco-subido")
commit(r, "base", BASE)
sh(r, "checkout", "-q", "-b", "resiliencia-parse")
commit(r, "spec resiliencia-parse", {"specs/resiliencia-parse.md": spec(
    "Resiliência no parse de valor", "Baixo. Só evita que o job quebre com valor malformado.",
    "O cálculo não quebra quando o extrato traz um valor malformado.",
    "1. `py tests/test_receita.py` passa.")})
commit(r, "parse resiliente de valor\n\nValidado: py tests/test_receita.py -> ok", {
    "pipeline/receita.py": RECEITA.replace(
        "        v = float(p[\"valor\"])\n",
        "        try:\n            v = float(p[\"valor\"].replace(\",\", \".\"))\n        except ValueError:\n            v = 0.0\n"),
})
sh(r, "checkout", "-q", "main")

# ---------- 3. fechar: HEAD e base mudaram depois da revisão ----------
r = new_repo("fechar-head-divergente-do-revisado")
base = commit(r, "base", {**BASE, "specs/pending.md": "# Pendências\n", "README.md": "# receita\n"})
sh(r, "checkout", "-q", "-b", "desconto-vip")
DESC = RECEITA.replace("        total[s] = total.get(s, 0.0) + v\n",
                       "        if s == \"atacado\":\n            v = v * (1 - DESCONTO_ATACADO)\n        total[s] = total.get(s, 0.0) + v\n").replace(
    "import csv\n", "import csv\n\nDESCONTO_ATACADO = 0.10\n")
rev = commit(r, "desconto de 10% no atacado\n\nValidado: py tests/test_receita.py -> ok", {
    "specs/desconto-atacado.md": spec("Desconto no atacado", "Médio. Muda o total do comitê.",
                                      "Aplicar 10% de desconto à receita do atacado.",
                                      "1. Atacado = 180.0 na amostra. Checagem: `py tests/test_receita.py`."),
    "pipeline/receita.py": DESC,
    "tests/test_receita.py": TEST.replace('"atacado": 200.0', '"atacado": 180.0'),
})
head = commit(r, "ajusta desconto", {"pipeline/receita.py": DESC.replace("0.10", "0.15")})
sh(r, "checkout", "-q", "main")
main_novo = commit(r, "readme", {"README.md": "# receita\n\nPipeline de receita por segmento.\n"})
SHAS["fechar-head-divergente-do-revisado"] = {"base": base, "rev": rev, "head": head, "main_novo": main_novo}

# ---------- 5. revisar: segunda rodada ----------
r = new_repo("revisar-segunda-rodada-sem-repetir")
PED_ST = """
pedido_id,cliente_id,valor,status
10,1,100.0,ativo
11,1,50.0,ativo
12,2,200.0,ativo
13,3,,ativo
14,4,30.0,ativo
15,2,70.0,cancelado
16,3,40.0,
"""
commit(r, "base", {**BASE, "dados/pedidos.csv": PED_ST,
                   "tests/test_receita.py": TEST.replace('"varejo": 150.0, "atacado": 200.0', '"varejo": 190.0, "atacado": 270.0')})
sh(r, "checkout", "-q", "-b", "filtro-ativos")
commit(r, "spec filtro-ativos", {"specs/filtro-ativos.md": spec(
    "Só pedidos ativos", "Médio. Muda o total que vai para o comitê.",
    "Somar só pedidos com status `ativo`; qualquer outro status (inclusive vazio) é descartado e contado em `descartados['inativo']`.",
    "1. Na amostra `dados/pedidos.csv`: varejo 150.0, atacado 200.0, descartados inativo 2. Checagem: `py tests/test_receita.py`.")})
R1 = RECEITA.replace("    for p in pedidos:\n", "    for p in pedidos:\n        if p[\"status\"] != \"ativo\":\n            continue\n")
r1 = commit(r, "filtra ativos\n\nValidado: py tests/test_receita.py -> ok", {"pipeline/receita.py": R1, "tests/test_receita.py": TEST})
R2 = RECEITA.replace('descartados = {"sem_cliente": 0, "sem_valor": 0}',
                     'descartados = {"sem_cliente": 0, "sem_valor": 0, "inativo": 0}').replace(
    "    for p in pedidos:\n",
    "    for p in pedidos:\n        if p.get(\"status\") in (\"cancelado\", \"inativo\"):\n            descartados[\"inativo\"] += 1\n            continue\n")
T2 = TEST.replace('"varejo": 150.0', '"varejo": 190.0').replace(
    '{"sem_cliente": 1, "sem_valor": 1}', '{"sem_cliente": 1, "sem_valor": 1, "inativo": 1}').replace(
    "assert t == {", "# status vazio conta como ativo\n    assert t == {")
r2 = commit(r, "conta descartados por status\n\nValidado: py tests/test_receita.py -> ok", {"pipeline/receita.py": R2, "tests/test_receita.py": T2})
sh(r, "checkout", "-q", "main")
SHAS["revisar-segunda-rodada-sem-repetir"] = {"r1": r1, "r2": r2}

# ---------- 6. revisar: branch limpa com iscas de estilo ----------
r = new_repo("revisar-limpo-com-iscas-de-estilo")
RECEITA_TODO = RECEITA.replace("def ler(caminho):\n", "def ler(caminho):\n    # TODO: limpar depois\n")
commit(r, "base", {**BASE, "pipeline/receita.py": RECEITA_TODO})
sh(r, "checkout", "-q", "-b", "valor-minimo")
commit(r, "spec valor-minimo", {"specs/valor-minimo.md": spec(
    "Valor mínimo por pedido", "Baixo. Parâmetro opcional; o padrão não muda o resultado.",
    "Aceitar `valor_minimo` opcional em `receita_por_segmento`; pedidos abaixo dele são descartados e contados em `descartados['abaixo_minimo']`.",
    "1. Sem o parâmetro, o resultado não muda (varejo 150.0, atacado 200.0). Com `valor_minimo=60`: varejo 100.0, atacado 200.0, abaixo_minimo 1. Checagem: `py tests/test_receita.py`.")})
CLEAN = RECEITA_TODO.replace("def receita_por_segmento(pedidos, clientes):",
                             "def receita_por_segmento(pedidos, clientes, valor_minimo=None):").replace(
    'descartados = {"sem_cliente": 0, "sem_valor": 0}',
    'descartados = {"sem_cliente": 0, "sem_valor": 0, "abaixo_minimo": 0}').replace(
    "        s = seg[p[\"cliente_id\"]]\n",
    "        if valor_minimo is not None and v < valor_minimo:\n            descartados[\"abaixo_minimo\"] += 1; continue\n        s = seg[p[\"cliente_id\"]]\n")
TCLEAN = """
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pipeline.receita import ler, receita_por_segmento


def test_total():
    t, d = receita_por_segmento(ler("dados/pedidos.csv"), ler("dados/clientes.csv"))
    assert t == {"varejo": 150.0, "atacado": 200.0}, t
    assert d == {"sem_cliente": 1, "sem_valor": 1, "abaixo_minimo": 0}, d


def test_min():
    res, cnt = receita_por_segmento(ler("dados/pedidos.csv"), ler("dados/clientes.csv"), valor_minimo=60)
    assert res == {"varejo": 100.0, "atacado": 200.0}, res; assert cnt == {"sem_cliente": 1, "sem_valor": 1, "abaixo_minimo": 1}, cnt


if __name__ == "__main__":
    test_total(); test_min(); print("ok")
"""
commit(r, "valor minimo opcional\n\nValidado: py tests/test_receita.py -> ok", {"pipeline/receita.py": CLEAN, "tests/test_receita.py": TCLEAN})
sh(r, "checkout", "-q", "main")

# ---------- GPT6. revisar: teste reescrito de forma equivalente (falso positivo) ----------
r = new_repo("revisar-teste-equivalente")
commit(r, "base", {**BASE, "specs/explicitar-teste.md": spec(
    "Explicitar o teste de total", "Baixo. Só muda o teste.",
    "Deixar explícito no teste quais segmentos existem e o valor de cada um.",
    "1. A saída é exatamente varejo 150.0 e atacado 200.0, sem outras chaves. Checagem: `py tests/test_receita.py`.")})
sh(r, "checkout", "-q", "-b", "explicitar-teste")
commit(r, "explicita asserts do total\n\nValidado: py tests/test_receita.py -> ok", {
    "tests/test_receita.py": TEST.replace(
        '    assert t == {"varejo": 150.0, "atacado": 200.0}, t\n',
        '    assert set(t) == {"varejo", "atacado"}, t\n    assert t["varejo"] == 150.0\n    assert t["atacado"] == 200.0\n')})
sh(r, "checkout", "-q", "main")

# ---------- 9. promover-regra: ocorrência única ----------
r = new_repo("promover-regra-trava-ocorrencia-unica")
commit(r, "base", BASE)

(OUT / "shas.json").write_text(json.dumps(SHAS, indent=2), encoding="utf-8")
print(json.dumps(SHAS, indent=2))
