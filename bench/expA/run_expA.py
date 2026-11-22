"""Experimento A: qualidade e custo de revisores.
Uso: py -I run_expA.py <saida> [--attempts N] [--arms a,b] [--cases x,y]
Cada execução recebe uma cópia limpa da fixture numa pasta temporária fora deste repositório (ou em BENCH_RUNS), para o
agente não alcançar o gabarito, os graders nem os resultados de outras execuções. Nada é escrito nas fixtures originais.
--set reserva roda o lote reservado (cases_reserva.json), que só se executa com a versão candidata congelada."""
import argparse, json, os, pathlib, re, shutil, stat, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor

W = pathlib.Path(__file__).resolve().parents[1]
SKILL = pathlib.Path(__file__).resolve().parents[2] / "skills/review/SKILL.md"
UPSTREAM = W / "upstream/review/SKILL.md"
SHAS = json.loads((W / "fixtures/shas.json").read_text(encoding="utf-8"))
RUNS = pathlib.Path(os.environ.get("BENCH_RUNS") or tempfile.gettempdir()).resolve() / "pipe-bench-runs/expA"
if RUNS.is_relative_to(W.parent):
    raise SystemExit(f"BENCH_RUNS precisa ficar fora do repositório: {RUNS}")

ROUND2 = ("previous round: branch SHA {r1}, target SHA {target}; findings: (1) blocker: the status filter dropped orders without counting them "
          "-> fixed in {r2}; (2) in scope: replace the dict of dropped counts with a dataclass -> dismissed: the spec "
          "asks for a minimal change and the rest of the code uses dict")


def body(text):
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onexc=lambda f, x, e: (os.chmod(x, stat.S_IWRITE), f(x)))


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def inputs(case, repo):
    args = f"branch {case['spec']} {repo.as_posix()} {case['branch']} {case['target']}"
    ref = git(repo, "log", "--format=%H", "-1", case["target"], "--", case["spec"])
    if ref:
        args += f" {ref}:{case['spec']}"
    if case.get("round2"):
        s = SHAS["revisar-segunda-rodada-sem-repetir"]
        target = git(repo, "merge-base", s["r1"], case["target"])
        args += " " + ROUND2.format(r1=s["r1"], r2=s["r2"], target=target)
    return args


def brief_ours(case, repo):
    return body(SKILL.read_text(encoding="utf-8")).replace("$ARGUMENTS", inputs(case, repo))


def brief_upstream(case, repo):
    b = body(UPSTREAM.read_text(encoding="utf-8"))
    return (b + f"\n\nInputs: review branch `{case['branch']}` against `{case['target']}` in the repository at {repo.as_posix()}. "
            f"There is no issue tracker: the specification is the file `{case['spec']}`. Read it instead of an issue.")


def child_env():
    # Sem variáveis da sessão do Claude Code que lança o bench nem chaves de API; a autenticação vem do login do CLI.
    return {k: v for k, v in os.environ.items() if not re.search(r"KEY|SECRET|TOKEN", k, re.I) and not k.startswith("CLAUDE")}


def run(cmd, cwd, stdin_text, timeout, env=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, input=stdin_text, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr, time.time() - t0
    except subprocess.TimeoutExpired as e:
        return -9, e.stdout or "", f"TIMEOUT after {timeout}s", time.time() - t0


def arm_astra(brief, repo, out):
    cmd = ["codex", "exec", "-m", "gpt-6.2-astra", "-c", "model_reasoning_effort=max", "--sandbox", "read-only",
           "--skip-git-repo-check", "--ephemeral", "--json", "-C", str(repo), "-o", str(out / "report.md"), "-"]
    rc, so, se, dt = run(cmd, repo, brief, 3600)
    (out / "events.jsonl").write_text(so, encoding="utf-8"); (out / "stderr.txt").write_text(se, encoding="utf-8")
    usage = {}
    for line in so.splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        u = ev.get("usage") or (ev.get("msg") or {}).get("usage") if isinstance(ev, dict) else None
        if isinstance(u, dict):
            for k, v in u.items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
    return rc, dt, usage, None


def arm_neon(brief, repo, out):
    cmd = ["agy", "-p", brief, "--model", "gemini-4-neon-xhigh", "--output-format", "json", "--print-timeout", "55m"]
    rc, so, se, dt = run(cmd, repo, "", 3600)
    (out / "raw.json").write_text(so, encoding="utf-8"); (out / "stderr.txt").write_text(se, encoding="utf-8")
    try:
        d = json.loads(so)
    except Exception:
        d = {}
    (out / "report.md").write_text(d.get("response") or "", encoding="utf-8")
    if d.get("status") not in (None, "SUCCESS"):
        rc = rc or 1
    return rc, dt, d.get("usage") or {}, None


def arm_claude(brief, repo, out):
    cmd = ["claude", "-p", "--model", "opus", "--effort", "max", "--output-format", "json",
           "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
           "--allowedTools", "Bash Read Glob Grep", "--disallowedTools", "Edit Write Agent Skill"]
    rc, so, se, dt = run(cmd, repo, brief, 3600, child_env())
    (out / "raw.json").write_text(so, encoding="utf-8"); (out / "stderr.txt").write_text(se, encoding="utf-8")
    try:
        d = json.loads(so)
    except Exception:
        d = {}
    (out / "report.md").write_text(d.get("result") or "", encoding="utf-8")
    return rc, dt, d.get("usage") or {}, d.get("total_cost_usd")


ARMS = {
    "astra-max": (arm_astra, brief_ours),
    "upstream-astra-max": (arm_astra, brief_upstream),
    "neon-xhigh": (arm_neon, brief_ours),
    "neon-xhigh-ptbr": (arm_neon, brief_ours),
    "upstream-neon-xhigh": (arm_neon, brief_upstream),
    "opus-max": (arm_claude, brief_ours),
    "upstream-opus-max": (arm_claude, brief_upstream),
}
CODEX_LANE = threading.Semaphore(4)
NEON_LANE = threading.Semaphore(10)
CLAUDE_LANE = threading.Semaphore(1)
LANES = {
    "astra-max": CODEX_LANE,
    "upstream-astra-max": CODEX_LANE,
    "neon-xhigh": NEON_LANE,
    "neon-xhigh-ptbr": NEON_LANE,
    "upstream-neon-xhigh": NEON_LANE,
    "opus-max": CLAUDE_LANE,
    "upstream-opus-max": CLAUDE_LANE,
}


def one(case, arm, n, root):
    out = root / case["id"] / f"{arm}-{n}"
    if (out / "meta.json").exists():
        return
    rmtree(out); out.mkdir(parents=True)
    repo = RUNS / case["id"] / f"{arm}-{n}"
    rmtree(repo); repo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(W / case["fixture"], repo)
    subprocess.run(["git", "switch", "--quiet", case["branch"]], cwd=repo, check=True)
    fn, bf = ARMS[arm]
    brief = bf(case, repo)
    (out / "brief.md").write_text(brief, encoding="utf-8")
    with LANES[arm]:
        rc, dt, usage, cost = fn(brief, repo, out)
    status = git(repo, "status", "--porcelain")
    meta = {"case": case["id"], "arm": arm, "attempt": n, "exit": rc, "seconds": round(dt, 1), "usage": usage,
            "cost_usd_reported": cost, "repo_dirty": bool(status.strip()), "git_status": status[:500],
            "case_set": "reserva" if case["fixture"].startswith("fixtures/reserva-") else "dev", "brief_sha": __import__("hashlib").sha256(brief.encode()).hexdigest()[:12], "skill_sha": __import__("hashlib").sha256(SKILL.read_bytes()).hexdigest()[:12], "report_chars": len((out / "report.md").read_text(encoding="utf-8")) if (out / "report.md").exists() else 0}
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(case["id"], arm, n, rc, round(dt), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--arms", default=",".join(ARMS)); ap.add_argument("--cases", default="")
    ap.add_argument("--set", choices=["dev", "reserva"], default="dev")
    a = ap.parse_args()
    CASES = json.loads((W / ("expA/cases.json" if a.set == "dev" else "expA/cases_reserva.json")).read_text(encoding="utf-8"))["cases"]
    root = pathlib.Path(a.out).resolve(); root.mkdir(parents=True, exist_ok=True)
    cases = [c for c in CASES if not a.cases or c["id"] in a.cases.split(",")]
    jobs = [(c, arm, n) for n in range(1, a.attempts + 1) for c in cases for arm in a.arms.split(",")]
    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(lambda j: one(*j, root), jobs))
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
