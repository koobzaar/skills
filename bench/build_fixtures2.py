"""Lote 2. Uso: py -I build_fixtures2.py <dir-saida>  (reaproveita helpers do lote 1)"""
import json, pathlib, subprocess, sys
sys.argv = [sys.argv[0], sys.argv[1]]
src = pathlib.Path(__file__).with_name("build_fixtures.py").read_text(encoding="utf-8")
helpers = src.split("# ---------- 1. revisar")[0]
exec(helpers)  # define OUT, sh, write, commit, new_repo, BASE, AGENTS, RECEITA, TEST, spec, SHAS

# ---------- implementar e2e com escalada ----------
r = new_repo("implementar-e2e-com-escalada")
commit(r, "base", {**BASE, "specs/receita-liquida.md": """
# Receita líquida com estornos

## Risco
Médio. O total líquido vai para o comitê junto da receita bruta.

## Objetivo
Calcular a receita líquida total, em que estornos (valor negativo) reduzem o total em vez de derrubar o cálculo.

## Fora do escopo
Mudar `receita_por_segmento` ou a regra de pedidos sem valor ou sem cliente.

## Decisões
- Função nova `liquido(valores)` em `pipeline/liquido.py`, que soma com sinal: o estorno entra negativo, porque o comitê quer o líquido.
- `receita_liquida(pedidos, clientes)` em `pipeline/receita.py` aplica `liquido` aos valores dos pedidos válidos (com cliente e com valor), sem passar por `receita_por_segmento`, que recusa negativos.

## Critérios de aceite
1. `liquido` soma com sinal. Checagem: `py -B -c "from pipeline.liquido import liquido; assert liquido([100,-20])==80; assert liquido([-20,10])==-10; print('ok')"` (contas feitas à mão).
2. Na amostra `dados/`, `receita_liquida` dá 350.0; com um estorno de -20.0 do cliente 1 acrescentado em memória, dá 330.0. Checagem: `py -B tests/test_liquida.py` (a criar no passo 2).
3. O comportamento atual não muda. Checagem: `py -B tests/test_receita.py`.

## Passos
1. Criar `pipeline/liquido.py` com `liquido(valores)`.
2. Criar `receita_liquida` em `pipeline/receita.py` e `tests/test_liquida.py`.

## Pontos abertos
Nenhum.
"""})

# ---------- fechar caminho feliz ----------
r = new_repo("fechar-squash-feliz")
base = commit(r, "base", {**BASE, "specs/pending.md": "# Pendências\n\n- `cliente_id` duplicado em `clientes.csv` sobrescreve o segmento anterior sem aviso em `receita_por_segmento` (origem: auditoria-base).\n",
                          "specs/receita-total.md": spec("Receita total", "Alto. O total vai para `fin.receita_segmento` e para o comitê.",
                                                         "Expor `receita_total(pedidos, clientes)` devolvendo `(soma_dos_segmentos, descartados)`.",
                                                         "1. Na amostra `dados/`, `receita_total` devolve `(350.0, {'sem_cliente': 1, 'sem_valor': 1})` (150 + 200, conta à mão). Checagem: `py -B tests/test_total.py`.")})
sh(r, "checkout", "-q", "-b", "receita-total")
TT = """
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pipeline.receita import ler, receita_total

if __name__ == "__main__":
    v, d = receita_total(ler("dados/pedidos.csv"), ler("dados/clientes.csv"))
    assert v == 350.0, v
    assert d == {"sem_cliente": 1, "sem_valor": 1}, d
    print(v, d)
"""
a1 = commit(r, "receita_total\n\nValidated: py -B tests/test_total.py -> 350.0 {'sem_cliente': 1, 'sem_valor': 1}", {
    "pipeline/receita.py": RECEITA + "\n\ndef receita_total(pedidos, clientes):\n    total, descartados = receita_por_segmento(pedidos, clientes)\n    return sum(total.values()), descartados\n",
    "tests/test_total.py": TT})
sh(r, "checkout", "-q", "main")
bare = OUT / "fechar-squash-feliz-remote.git"
import shutil, os, stat
if bare.exists():
    shutil.rmtree(bare, onexc=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
subprocess.run(["git", "clone", "-q", "--bare", str(r), str(bare)], check=True)
sh(r, "remote", "add", "origin", str(bare))
sh(r, "fetch", "-q", "origin")
sh(r, "branch", "-q", "--set-upstream-to=origin/main", "main")
SHAS["fechar-squash-feliz"] = {"base": base, "head": a1}

# ---------- spec arredondamento ----------
r = new_repo("spec-arredondamento-no-consumidor")
commit(r, "base", {**BASE, "consumidor/README.md": "O financeiro lê `relatorios/segmentos.csv` (segmento,receita) para decidir repasses. A receita é decimal com duas casas.\n"})

# ---------- preparar-repo com REVIEW.md existente ----------
r = new_repo("preparar-repo-com-review-existente")
b = {k: v for k, v in BASE.items() if k != "AGENTS.md"}
commit(r, "base", {**b,
    "README.md": "# receita\n\n`dados/` é um extrato real. Não use para validação local. O comitê consome `fin.receita_segmento`. Ignorar `build/` nas revisões.\n",
    "REVIEW.md": "# Revisão\n\n- Bloqueia divergência com o fechamento mensal ou pedido descartado sem aviso.\n- Caminho sensível: `fin.receita_segmento`.\n",
    "tests/test_fumaca.py": "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\nfrom pipeline.receita import receita_por_segmento\n\nif __name__ == \"__main__\":\n    assert receita_por_segmento([], []) == ({}, {\"sem_cliente\": 0, \"sem_valor\": 0})\n    print(\"ok\")\n",
    "build/saida.txt": "gerado\n"})

# ---------- estado-final (controle) ----------
r = new_repo("estado-final-preserva-contrato")
commit(r, "base", {**BASE, "specs/segmento-desconhecido.md": """
# Segmento desconhecido

Primeiro usamos o bucket `outros`.
A decisão atual é usar `desconhecido`, porque o financeiro concilia faltas de cadastro separadamente.

## Critérios de aceite
1. Pedido válido sem cadastro cai em `desconhecido`.
2. A receita total é conservada.

No teste antigo, o pedido caía em `outros`.

## Plano
1. Atualizar o mapeamento.
2. Testar a conservação da receita.
"""})

(OUT / "shas2.json").write_text(json.dumps(SHAS, indent=2), encoding="utf-8")
print(json.dumps(SHAS, indent=2))
