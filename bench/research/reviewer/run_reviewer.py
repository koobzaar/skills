"""Mede o passo de revisão da skill research: um relatório cujos trechos passam no verify, com uma evidência
(E2) literal que não sustenta a afirmação. O revisor deve marcar E2 como "não apoia" e não marcar E1 e E3.

Uso: py -I -B bench/research/reviewer/run_reviewer.py <saida> [--attempts 1] [--model gemini-4-neon-medium]
Precisa de bench/research/corpus.jsonl e do CLI agy autenticado."""
import argparse, json, pathlib, re, shutil, subprocess, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DOIS = {"doi:10.1093/pubmed/fdab161", "doi:10.59139/stattrans-2025-024"}
EXPECT = {"E1": False, "E2": True, "E3": False}  # True: deve ser marcada como "não apoia"


def profile_body():
    t = (ROOT / "agents/reviewer.md").read_text(encoding="utf-8")
    return t.split("---", 2)[2].strip()


def task():
    s = (ROOT / "skills/research/SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"Depois peça ao subagente `reviewer` que (.+?)\. Revise", s, re.S)
    if not m:
        raise SystemExit("não achei o pedido ao reviewer no SKILL.md")
    return ("Leia o relatório research/relatorio.md e o registro research/papers.jsonl, e " + m.group(1) +
            ". Responda uma linha por evidência, começando pelo rótulo (E1, E2...).")


def grade(text):
    res = {}
    for e, want_flag in EXPECT.items():
        line = next((l for l in text.splitlines() if re.search(rf"\b{e}\b", l)), "")
        flagged = bool(re.search(r"n[aã]o apoia", line, re.I))
        res[e] = (flagged == want_flag, line.strip()[:160] or "sem linha")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--attempts", type=int, default=1); ap.add_argument("--model", default="gemini-4-neon-medium")
    a = ap.parse_args()
    corpus = [json.loads(l) for l in (ROOT / "bench/research/corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    prompt = profile_body() + "\n\n" + task()
    for n in range(1, a.attempts + 1):
        out = pathlib.Path(a.out).resolve() / f"reviewer-{n}"
        out.mkdir(parents=True, exist_ok=True)
        repo = pathlib.Path(tempfile.gettempdir()) / "research-bench" / "reviewer" / str(n)
        shutil.rmtree(repo, ignore_errors=True)
        (repo / "research").mkdir(parents=True)
        shutil.copy(HERE / "relatorio.md", repo / "research/relatorio.md")
        (repo / "research/papers.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in corpus if DOIS & set(r["ids"])), encoding="utf-8")
        (out / "prompt.txt").write_text(prompt, encoding="utf-8")
        t0 = time.time()
        p = subprocess.run([shutil.which("agy") or "agy", "-p", prompt, "--model", a.model, "--output-format", "json", "--print-timeout", "20m"],
                           cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500)
        (out / "raw.json").write_text(p.stdout, encoding="utf-8"); (out / "stderr.txt").write_text(p.stderr, encoding="utf-8")
        try:
            d = json.loads(p.stdout)
        except ValueError:
            d = {}
        text = d.get("response") or ""
        (out / "report.md").write_text(text, encoding="utf-8")
        res = grade(text)
        meta = {"model": a.model, "exit": p.returncode, "seconds": round(time.time() - t0, 1), "usage": d.get("usage") or {},
                "result": {k: {"pass": ok, "line": l} for k, (ok, l) in res.items()}}
        (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"reviewer #{n} {a.model} rc={p.returncode} " + "; ".join(f"{k}={'ok' if ok else 'FALHA'}" for k, (ok, _) in res.items()), flush=True)


if __name__ == "__main__":
    main()
