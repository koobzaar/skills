"""Bench da skill research no Claude Code: `claude -p` com e sem a skill, sobre o corpus local.

Uso:
  py -I -B bench/research/run_claude.py <saida> --set bench/research/hard --cases autocontrole --arms with
  py -I -B bench/research/run_claude.py <saida> --probe --model haiku   # só lista skills, plugins, ferramentas e MCP

Cada execução roda numa pasta temporária com git próprio, fora deste repositório, para o agente não ver o AGENTS.md,
o gabarito nem os graders. Os dois braços recebem o mesmo tools/lit.py, o mesmo pedido, o mesmo modelo e o mesmo
esforço; o braço com skill tem .claude/skills/research/SKILL.md e "/research" no início do pedido. Só as
configurações do projeto temporário são carregadas, sem servidores MCP, sem WebSearch, WebFetch, o subagente web-fetch
e as ferramentas que falam com outras sessões. Uma execução
por vez; --max-budget-usd interrompe a que passar do limite."""
import argparse, hashlib, json, os, pathlib, re, shutil, stat, subprocess, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SKILL = ROOT / "skills/research/SKILL.md"
SKILL_SHA = hashlib.sha256(SKILL.read_bytes() + (ROOT / "skills/research/lit.py").read_bytes()).hexdigest()[:12]
WORK = pathlib.Path(tempfile.gettempdir()) / "research-bench-claude"
BLOCKED = ["WebSearch", "WebFetch", "Agent(web-fetch)", "Task(web-fetch)", "SendMessage", "ListAgents", "RemoteTrigger",
           "PushNotification", "CronCreate", "ScheduleWakeup", "DesignSync"]


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
    (repo / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "skills/research/lit.py", repo / "tools/lit.py")
    for rel, text in (files or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    if with_skill:
        d = repo / ".claude/skills/research"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(skill_text(), encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=repo, check=True)


def child_env(corpus):
    # Sem chaves de API nem variáveis da sessão do Claude Code que lança o bench; a autenticação vem do login do CLI.
    env = {k: v for k, v in os.environ.items() if not re.search(r"KEY|SECRET|TOKEN", k, re.I) and not k.startswith("CLAUDE")}
    if corpus:
        env["LIT_CORPUS"] = str(corpus)
    return env


def claude_cmd(model, effort, budget):
    return [shutil.which("claude") or "claude", "-p", "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config", "--disallowedTools", *BLOCKED,
            "--permission-mode", "bypassPermissions", "--max-budget-usd", str(budget)]


def run(cmd, prompt, cwd, env, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=prompt, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        so, se, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        so = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        se, rc = "TIMEOUT", -9
    return so, se, rc, time.time() - t0


def events(text):
    for line in text.splitlines():
        try:
            yield json.loads(line)
        except ValueError:
            continue


def probe(out, model, effort, budget):
    repo = WORK / "probe"
    prepare(repo, {}, with_skill=False)
    so, se, rc, dt = run(claude_cmd(model, effort, budget), "Responda só: ok", repo, child_env(None), 600)
    out.mkdir(parents=True, exist_ok=True)
    (out / "probe.jsonl").write_text(so, encoding="utf-8")
    init = next((e for e in events(so) if e.get("type") == "system" and e.get("subtype") == "init"), {})
    for k in ("model", "tools", "mcp_servers", "plugins", "skills", "slash_commands", "agents"):
        print(f"{k}: {init.get(k)}")
    print("rc", rc, f"{dt:.0f}s", se[-300:])


def run_one(cases, corpus, cid, arm, n, root, model, effort, budget):
    out = root / cid / f"{arm}-{n}"
    if (out / "meta.json").exists():
        return
    rmtree(out); out.mkdir(parents=True)
    spec = cases["cases"][cid]
    repo = WORK / cid / f"{arm}-{n}"
    prepare(repo, spec.get("files"), with_skill=(arm == "with"))
    prompt = spec["prompt"] + "\n\n" + cases["tool_note"]
    if arm == "with":
        prompt = "/research " + prompt
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    so, se, rc, dt = run(claude_cmd(model, effort, budget), prompt, repo, child_env(corpus), 2400)
    (out / "events.jsonl").write_text(so, encoding="utf-8")
    (out / "stderr.txt").write_text(se, encoding="utf-8")
    if (repo / "research").exists():
        shutil.copytree(repo / "research", out / "research")
    evs = list(events(so))
    res = next((e for e in reversed(evs) if e.get("type") == "result"), {})
    init = next((e for e in evs if e.get("type") == "system" and e.get("subtype") == "init"), {})
    (out / "final.md").write_text(res.get("result") or "", encoding="utf-8")
    meta = {"kind": "case", "case": cid, "arm": arm, "attempt": n, "exit": rc, "seconds": round(dt, 1), "usage": res.get("usage") or {},
            "cost_usd": res.get("total_cost_usd"), "num_turns": res.get("num_turns"), "result_subtype": res.get("subtype"),
            "model": init.get("model") or model, "effort": effort, "skill_sha": SKILL_SHA, "skills_loaded": init.get("skills"),
            "plugins_loaded": init.get("plugins"), "mcp_servers": init.get("mcp_servers"), "agent": "claude-code",
            "corpus_papers": sum(1 for _ in corpus.open(encoding="utf-8"))}
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(cid, arm, n, "rc", rc, f"{dt:.0f}s", "custo", meta["cost_usd"], "turnos", meta["num_turns"], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--set", default=str(HERE))
    ap.add_argument("--cases", default="")
    ap.add_argument("--arms", default="with,without")
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--budget", type=float, default=10.0, help="limite em USD por execução")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    root = pathlib.Path(a.out).resolve()
    if a.probe:
        return probe(root, a.model, a.effort, a.budget)
    d = pathlib.Path(a.set).resolve()
    cases, corpus = json.loads((d / "cases.json").read_text(encoding="utf-8")), d / "corpus.jsonl"
    if not corpus.exists():
        raise SystemExit("corpus ausente: rode bench/research/build_corpus.py --set " + str(d))
    for n in range(1, a.attempts + 1):
        for cid in filter(None, a.cases.split(",")):
            for arm in a.arms.split(","):
                run_one(cases, corpus, cid, arm, n, root, a.model, a.effort, a.budget)
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
