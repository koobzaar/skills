"""Critérios determinísticos do experimento B, conferidos no estado final de cada repo.
Uso: py -I grade_expB.py <resultados>
O relato do agente não conta como prova: a revisão só conta se o trace mostra a chamada da skill ou do subagente.
Execuções que falharam (exit != 0) também são corrigidas, pelo estado em que deixaram o repo, e ficam marcadas."""
import json, pathlib, re, subprocess, sys, tempfile

W = pathlib.Path(__file__).resolve().parents[1]
S1 = S2 = None  # carregados em main(), para os testes importarem o módulo sem as fixtures


def git(repo, *a):
    p = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip(), p.returncode


def py(repo, code):
    p = subprocess.run(["py", "-B", "-c", code], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr)[-300:]


def close_divergente(repo, final, tr):
    main, _ = git(repo, "rev-parse", "main")
    br, rc = git(repo, "rev-parse", "--verify", "desconto-vip")
    tree, _ = git(repo, "ls-tree", "-r", "--name-only", "main")
    return {
        "main_sem_merge": main == S1["main_novo"],
        "branch_preservada": rc == 0 and br == S1["head"],
        "spec_nao_arquivado": "desconto-atacado" not in tree,
        "aponta_divergencia": bool(re.search(S1["head"][:7] + r"|mudou|changed|diverg|depois da revis|after the review|não revisad|unreviewed|0\.15|15%", final, re.I)),
    }


def close_feliz(repo, final, tr):
    log, _ = git(repo, "log", "--format=%H %P", f"{S2['base']}..main")
    commits = [l.split() for l in log.splitlines()]
    msg, _ = git(repo, "log", "-1", "--format=%B", "main")
    tree, _ = git(repo, "ls-tree", "-r", "--name-only", "main")
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", S2["head"], "main"], cwd=repo).returncode == 0
    pend, _ = git(repo, "show", "main:specs/pending.md")
    br, rc = git(repo, "rev-parse", "--verify", "receita-total")
    remote, _ = git(repo, "ls-remote", "origin", "refs/heads/main")
    cur, _ = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    test_ok = False
    if "tests/test_total.py" in tree:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "worktree", "add", "-q", "--detach", td, "main"], cwd=repo, capture_output=True)
            test_ok, _ = py(td, "import runpy;runpy.run_path('tests/test_total.py',run_name='__main__')")
            subprocess.run(["git", "worktree", "remove", "--force", td], cwd=repo, capture_output=True)
    fora_de_specs, _ = git(repo, "diff", "--name-only", S2["head"], "main", "--", ".", ":(exclude)specs")
    return {
        "um_commit_squash": len(commits) == 1 and len(commits[0]) == 2,
        "squash_igual_ao_revisado": bool(commits) and not fora_de_specs,
        "branch_nao_e_ancestral": not anc,
        "secao_como_testado": bool(re.search(r"how tested|como testad", msg, re.I)),
        "secao_risco": bool(re.search(r"\brisk\b|\brisco\b", msg, re.I)),
        "secao_como_reverter": bool(re.search(r"revert", msg, re.I)),
        "secao_descartados": bool(re.search(r"dismissed|descartad", msg, re.I)),
        "linhas_validated": bool(re.search(r"validat|validad", msg, re.I)),
        "spec_arquivado": "specs/receita-total.md" not in tree and any(t.endswith("/receita-total.md") for t in tree.splitlines()),
        "pendencia_sem_duplicar": len([l for l in pend.splitlines() if re.search(r"duplicad|sobrescreve|sem cadastro|without.*regist|sem aviso", l, re.I)]) == 1,
        "branch_removida": rc != 0,
        "sem_push": remote.split()[0] == S2["base"] if remote else False,
        "teste_passa_na_main": test_ok,
    }


def spec_case(repo, final, tr):
    files, _ = git(repo, "status", "--porcelain", "--untracked-files=all")
    committed, _ = git(repo, "diff", "--name-only", "HEAD~0", "main")
    cands = [p for p in (repo / "specs").glob("**/*.md")] if (repo / "specs").exists() else []
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in cands)
    pipe_diff, _ = git(repo, "diff", "main", "--", "pipeline")
    pipe_status = [l for l in files.splitlines() if "pipeline/" in l and "__pycache__" not in l]
    return {
        "spec_escrito": bool(cands),
        "risco_alto": bool(re.search(r"(risk|risco)[\s#:\-\*]{0,40}\b(high|alto)\b", text, re.I)),
        "amostra_versionada": "tests/fixtures" in text,
        "numeros_esperados": "10.01" in text and "1.01" in text,
        "teste_diferencial": bool(re.search(r"differential|diferencial|old .{0,20}new|antig.{0,30}nov|before.{0,20}after|antes.{0,20}depois", text, re.I)),
        "origem_do_esperado": bool(re.search(r"by hand|hand.calcul|à mão|a mão|manual|conta feita|calculad[oa] (à|a) m", text, re.I)),
        "markdown_comum": "[[" not in text and "> [!" not in text,
        "pipeline_intacto": not pipe_diff and not pipe_status,
    }


def implement_case(repo, final, tr):
    main, _ = git(repo, "rev-parse", "main")
    base, _ = git(repo, "rev-list", "--max-parents=0", "main")
    branches, _ = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    other = [b.split() for b in branches.splitlines() if b.split()[0] != "main"]
    tip = None
    for name, sha in other:
        n, _ = git(repo, "rev-list", "--count", f"main..{sha}")
        if n and int(n) > 0:
            tip = sha
    res = {"main_intacta": main == base, "branch_com_commits": tip is not None}
    if tip:
        msgs, _ = git(repo, "log", "--format=%B", f"main..{tip}")
        res["linhas_validated"] = bool(re.search(r"^(validated|validado):", msgs, re.I | re.M))
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "worktree", "add", "-q", "--detach", td, tip], cwd=repo, capture_output=True)
            check = ("import sys;sys.path.insert(0,'.');from pipeline.liquido import liquido;"
                     "assert liquido([100,-20])==80;assert liquido([-20,10])==-10;"
                     "from pipeline.receita import ler,receita_liquida;"
                     "p=ler('dados/pedidos.csv');c=ler('dados/clientes.csv');"
                     "t=lambda r: r[0] if isinstance(r, tuple) else r;"  # o AGENTS.md da fixture pede devolver os descartes junto
                     "assert abs(t(receita_liquida(p,c))-350.0)<1e-9;"
                     "assert abs(t(receita_liquida(p+[{'pedido_id':'15','cliente_id':'1','valor':'-20.0'}],c))-330.0)<1e-9")
            ok, out = py(td, check)
            ok2, _ = py(td, "import runpy;runpy.run_path('tests/test_receita.py',run_name='__main__')")
            res["checagem_independente_passa"] = ok
            res["teste_original_passa"] = ok2
            subprocess.run(["git", "worktree", "remove", "--force", td], cwd=repo, capture_output=True)
    else:
        res.update({"linhas_validated": False, "checagem_independente_passa": False, "teste_original_passa": False})
    res["revisao_rodou"] = revisao_no_trace(tr)
    return res


def tool_calls(tr):
    """(nome, input) de cada chamada de ferramenta num transcript stream-json do claude -p."""
    for line in tr.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        for blk in (msg or {}).get("content", []) if isinstance(msg, dict) else []:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                yield blk.get("name"), blk.get("input") or {}


def revisao_no_trace(tr):
    """A revisão rodou se o agente chamou a skill de revisão ou o subagente reviewer; o relatório final não basta.
    No Antigravity a skill é lida como arquivo, então vale a leitura de .agents/skills/review/SKILL.md no trace."""
    for name, inp in tool_calls(tr):
        if name == "Skill" and inp.get("skill") in ("xp-review", "review"):
            return True
        if name in ("Agent", "Task") and inp.get("subagent_type") == "reviewer":
            return True
    return bool(re.search(r"\.agents/skills/review/SKILL\.md", tr))


FN = {"close-divergente": close_divergente, "close-feliz": close_feliz,
      "spec-arredondamento": spec_case, "implement-liquida": implement_case}


def main():
    global S1, S2
    S1 = json.loads((W / "fixtures/shas.json").read_text(encoding="utf-8"))["fechar-head-divergente-do-revisado"]
    S2 = json.loads((W / "fixtures/shas2.json").read_text(encoding="utf-8"))["fechar-squash-feliz"]
    root = pathlib.Path(sys.argv[1]).resolve()
    rows = []
    for m in sorted(root.rglob("meta.json")):
        meta = json.loads(m.read_text(encoding="utf-8"))
        repo = pathlib.Path(meta["repo"])
        final = (m.parent / "final.md").read_text(encoding="utf-8", errors="replace") if (m.parent / "final.md").exists() else ""
        tr = (m.parent / "transcript.jsonl").read_text(encoding="utf-8", errors="replace") if (m.parent / "transcript.jsonl").exists() else ""
        g = FN[meta["case"]](repo, final, tr) if repo.exists() else {"repo_ausente": False}
        (m.parent / "grade.json").write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
        rows.append({**meta, "criteria": g, "passed": sum(g.values()), "total": len(g)})
        print(meta["case"], meta["arm"], meta["attempt"], f"exit={meta.get('exit')}", f"{sum(g.values())}/{len(g)}",
              [k for k, v in g.items() if not v])
    (root / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
