"""Experimento B: skill contra sem skill, com claude -p como agente substituto do Devin CLI.
Uso: py -I run_expB.py <saida> [--attempts N] [--cases a,b]
As skills do plugin são instaladas na cópia da fixture como .claude/skills/xp-<nome>, para não colidir
com skills pessoais de mesmo nome. O braço sem skill recebe o mesmo pedido em linguagem natural."""
import argparse, json, os, pathlib, re, shutil, stat, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor

W = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = pathlib.Path(__file__).resolve().parents[2]
S1 = json.loads((W / "fixtures/shas.json").read_text(encoding="utf-8"))
S2 = json.loads((W / "fixtures/shas2.json").read_text(encoding="utf-8"))
import hashlib
NAMES = ["spec", "implement", "review", "close-spec"]
SKILL_SHA = hashlib.sha256(b"".join((PLUGIN / "skills" / n / "SKILL.md").read_bytes() for n in ["spec", "implement", "review", "close-spec"])).hexdigest()[:12]
fd, ff = S1["fechar-head-divergente-do-revisado"], S2["fechar-squash-feliz"]

BRAIN = ("Planeje a mudança de receita por segmento. O financeiro vai usar o CSV de segmentos (relatorios/segmentos.csv) "
         "para decidir repasses. Some os valores decimais por segmento e arredonde só no fim, com ROUND_HALF_UP; um segmento "
         "por linha, ordem livre. Preserve o comportamento atual para pedido sem cliente e valor vazio. Na amostra, use dois "
         "pedidos de varejo de 10.005 e 0.005 e um de atacado de 1.005, todos com cliente conhecido. Só quero o spec agora; "
         "pode gravar sem me perguntar.")
CASES = {
    "close-divergente": {"fixture": "fechar-head-divergente-do-revisado",
        "with": f"/xp-close-spec desconto-vip — o revisor deu pronto no commit {fd['rev']} com alvo e base {fd['base']} (spec specs/desconto-atacado.md, risco médio). Pode fazer o squash na main sem me perguntar. Não faça push.",
        "without": f"Fecha a branch desconto-vip na main com squash merge, arquivando o spec — o revisor deu pronto no commit {fd['rev']} com alvo e base {fd['base']} (spec specs/desconto-atacado.md, risco médio). Pode fazer sem me perguntar. Não faça push."},
    "close-feliz": {"fixture": "fechar-squash-feliz",
        "with": f"/xp-close-spec receita-total — o revisor deu pronto no commit {ff['head']} com alvo e base {ff['base']} (spec specs/receita-total.md, risco alto). Fora do escopo, reproduzido: pedido de cliente sem cadastro some sem aviso (pedido 14). Achado descartado: renomear receita_total para total_receita, porque o spec define o nome. Pode fechar sem me perguntar. Não faça push.",
        "without": f"Fecha a branch receita-total na main com squash merge, arquivando o spec e registrando as pendências — o revisor deu pronto no commit {ff['head']} com alvo e base {ff['base']} (spec specs/receita-total.md, risco alto). Fora do escopo, reproduzido: pedido de cliente sem cadastro some sem aviso (pedido 14). Achado descartado: renomear receita_total para total_receita, porque o spec define o nome. Pode fechar sem me perguntar. Não faça push."},
    "spec-arredondamento": {"fixture": "spec-arredondamento-no-consumidor",
        "with": "/xp-spec " + BRAIN,
        "without": "Escreve um spec em specs/ para esta mudança. " + BRAIN},
    "implement-liquida": {"fixture": "implementar-e2e-com-escalada",
        "with": "/xp-implement specs/receita-liquida.md — pode seguir sem me perguntar até o portão; não faça merge nem push.",
        "without": "Implementa o spec specs/receita-liquida.md numa branch própria. Pode seguir sem me perguntar; não faça merge nem push."},
}


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onexc=lambda f, x, e: (os.chmod(x, stat.S_IWRITE), f(x)))


def install(repo):
    for n in NAMES:
        dst = repo / ".claude/skills" / f"xp-{n}"
        dst.mkdir(parents=True)
        s = (PLUGIN / "skills" / n / "SKILL.md").read_text(encoding="utf-8")
        s = re.sub(r"^name: .*$", f"name: xp-{n}", s, count=1, flags=re.M)
        for m in NAMES:
            s = re.sub(rf"`{re.escape(m)}`", f"`xp-{m}`", s)
        s = re.sub(r"(?<![\w/-])/review", "/xp-review", s)
        # Devin roda `agent: reviewer` como subagente; no Claude Code o equivalente pede `context: fork`.
        s = s.replace("\nagent: reviewer\n", "\ncontext: fork\nagent: reviewer\n")
        (dst / "SKILL.md").write_text(s, encoding="utf-8")
    (repo / ".claude/agents").mkdir(parents=True, exist_ok=True)
    shutil.copy(PLUGIN / "agents/explorer.md", repo / ".claude/agents/explorer.md")
    # O Claude Code só roda modelos Claude: o revisor substituto usa Opus com o mesmo texto do perfil do Devin.
    rv = (PLUGIN / "agents/reviewer.md").read_text(encoding="utf-8")
    rv = re.sub(r"^model: .*$", "model: opus", rv, count=1, flags=re.M)
    (repo / ".claude/agents/reviewer.md").write_text(rv, encoding="utf-8")
    with open(repo / ".git/info/exclude", "a", encoding="utf-8") as f:
        f.write(".claude/\n")


LANE = threading.Semaphore(2)


def one(cid, arm, n, root):
    c = CASES[cid]
    out = root / cid / f"{arm}-{n}"
    if (out / "meta.json").exists():
        return
    rmtree(out); out.mkdir(parents=True)
    repo = W / "runs/expB" / cid / f"{arm}-{n}"
    rmtree(repo); rmtree(repo.with_name(repo.name + "-remote.git")); repo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(W / "fixtures" / c["fixture"], repo)
    remote = W / "fixtures" / (c["fixture"] + "-remote.git")
    if remote.exists():
        r2 = repo.with_name(repo.name + "-remote.git"); shutil.copytree(remote, r2)
        subprocess.run(["git", "remote", "set-url", "origin", str(r2)], cwd=repo)
    if arm == "with":
        install(repo)
    cmd = ["claude", "-p", "--model", "opus", "--output-format", "stream-json", "--verbose",
           "--allowedTools", "Bash Read Edit Write Glob Grep Agent Skill", "--permission-mode", "acceptEdits"]
    with LANE:
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=repo, input=c[arm], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=3600)
            so, se, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            so, se, rc = e.stdout or "", "TIMEOUT", -9
        dt = time.time() - t0
    (out / "transcript.jsonl").write_text(so, encoding="utf-8"); (out / "stderr.txt").write_text(se, encoding="utf-8")
    final, cost, skills = "", None, []
    for line in so.splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "result":
            final, cost = ev.get("result", ""), ev.get("total_cost_usd")
        for blk in (ev.get("message") or {}).get("content", []) if isinstance(ev.get("message"), dict) else []:
            if isinstance(blk, dict) and blk.get("type") == "tool_use" and blk.get("name") == "Skill":
                skills.append((blk.get("input") or {}).get("skill"))
    (out / "final.md").write_text(final or "", encoding="utf-8")
    meta = {"case": cid, "arm": arm, "attempt": n, "exit": rc, "seconds": round(dt, 1), "cost_usd": cost,
            "skills_invoked": skills, "repo": str(repo), "skill_sha": SKILL_SHA}
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(cid, arm, n, rc, round(dt), cost, flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out")
    ap.add_argument("--attempts", type=int, default=2); ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args(); root = pathlib.Path(a.out).resolve()
    jobs = [(c, arm, n) for n in range(1, a.attempts + 1) for c in a.cases.split(",") for arm in ("with", "without")]
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda j: one(*j, root), jobs))
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
