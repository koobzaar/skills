"""Bench da skill research: codex exec com e sem a skill, sobre o corpus local e sem rede.

Uso:
  py -I -B bench/research/run_research.py <saida> --cases ja-feito,premissa-contradita --arms with,without [--attempts 1]
  py -I -B bench/research/run_research.py <saida> --triggers positivo-novidade,negativo-explicar
  --set bench/research/hard   usa o cases.json e o corpus.jsonl de outra pasta

As cópias rodam numa pasta temporária fora deste repositório, cada uma com git próprio, para o agente não ler o
AGENTS.md daqui. Os dois braços recebem o mesmo tools/lit.py e o mesmo pedido; o braço com skill tem
.agents/skills/research/SKILL.md e "$research" no início do pedido. Nos casos de acionamento, a skill está instalada
e não é mencionada. Execuções sequenciais."""
import argparse, hashlib, json, os, pathlib, re, shutil, stat, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
CORPUS = HERE / "corpus.jsonl"
MODEL, EFFORT = "gpt-6.2-sol", "medium"
SKILL = ROOT / "skills/research/SKILL.md"
SKILL_SHA = hashlib.sha256(SKILL.read_bytes() + (ROOT / "skills/research/lit.py").read_bytes()).hexdigest()[:12]
WORK = pathlib.Path(tempfile.gettempdir()) / "research-bench"


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onexc=lambda f, x, e: (os.chmod(x, stat.S_IWRITE), f(x)))


def skill_text():
    s = SKILL.read_text(encoding="utf-8")
    new, n = re.subn(r"que fica ao lado deste arquivo: .*? na instalação global\.", "que fica em `tools/lit.py`.", s, count=1)
    if n != 1:
        raise SystemExit("não achei a frase do caminho do lit.py no SKILL.md; ajuste skill_text()")
    return new


def prepare(repo, files, with_skill):
    rmtree(repo)
    repo.mkdir(parents=True)
    (repo / "tools").mkdir()
    shutil.copy(ROOT / "skills/research/lit.py", repo / "tools/lit.py")
    for rel, text in (files or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    if with_skill:
        d = repo / ".agents/skills/research"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(skill_text(), encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=repo, check=True)


def run_one(kind, cid, arm, n, root):
    out = root / cid / f"{arm}-{n}"
    if (out / "meta.json").exists():
        return
    rmtree(out); out.mkdir(parents=True)
    spec = CASES["cases"][cid] if kind == "case" else CASES["triggers"][cid]
    repo = WORK / cid / f"{arm}-{n}"
    prepare(repo, spec.get("files"), with_skill=(arm == "with"))
    # Nos acionamentos, só a skill aponta a ferramenta: a nota induziria busca até em pedidos que não pedem literatura.
    prompt = spec["prompt"] + ("\n\n" + CASES["tool_note"] if kind == "case" else "")
    if kind == "case" and arm == "with":
        prompt = "$research " + prompt
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not re.search(r"KEY|SECRET|TOKEN", k, re.I) or k.startswith("CODEX") or k == "OPENAI_API_KEY"}
    env["LIT_CORPUS"] = str(CORPUS)
    cmd = [shutil.which("codex") or "codex", "exec", "-m", MODEL, "-c", f"model_reasoning_effort={EFFORT}", "--sandbox", "workspace-write",
           "-c", "sandbox_workspace_write.network_access=false", "-c", "web_search=\"disabled\"", "--skip-git-repo-check", "--ephemeral", "--json",
           "-C", str(repo), "-o", str(out / "final.md"), "-"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=1800)
        so, se, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        so, se, rc = e.stdout or "", "TIMEOUT", -9
    dt = time.time() - t0
    (out / "events.jsonl").write_text(so, encoding="utf-8")
    (out / "stderr.txt").write_text(se, encoding="utf-8")
    if (repo / "research").exists():
        shutil.copytree(repo / "research", out / "research")
    usage = {}
    for line in so.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        u = ev.get("usage") if isinstance(ev, dict) else None
        if isinstance(u, dict):
            for k, v in u.items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
    meta = {"kind": kind, "case": cid, "arm": arm, "attempt": n, "exit": rc, "seconds": round(dt, 1), "usage": usage,
            "model": MODEL, "effort": EFFORT, "agent": "codex", "skill_sha": SKILL_SHA, "corpus_papers": sum(1 for _ in CORPUS.open(encoding="utf-8"))}
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(kind, cid, arm, n, "rc", rc, f"{dt:.0f}s", usage, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cases", default="")
    ap.add_argument("--triggers", default="")
    ap.add_argument("--arms", default="with,without")
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--set", default=str(HERE))
    a = ap.parse_args()
    global CASES, CORPUS
    d = pathlib.Path(a.set).resolve()
    CASES, CORPUS = json.loads((d / "cases.json").read_text(encoding="utf-8")), d / "corpus.jsonl"
    if not CORPUS.exists():
        raise SystemExit("corpus ausente: rode bench/research/build_corpus.py")
    root = pathlib.Path(a.out).resolve()
    for n in range(1, a.attempts + 1):
        for cid in filter(None, a.cases.split(",")):
            for arm in a.arms.split(","):
                run_one("case", cid, arm, n, root)
        for cid in filter(None, a.triggers.split(",")):
            run_one("trigger", cid, "with", n, root)
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
