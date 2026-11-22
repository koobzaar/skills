"""Avalia os relatórios do experimento A contra o gabarito de cases.json.
Uso: py -I grade_expA.py <resultados> [sonnet|sol]
Grader: claude -p --model sonnet, uma chamada por relatório, saída JSON. O grader recebe o gabarito e o
relatório, nunca o nome do revisor. Um parser por regex do veredito roda junto, para medir a concordância."""
import shutil, json, pathlib, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

W = pathlib.Path(__file__).resolve().parents[1]
CASES = {c["id"]: c for c in json.loads((W / "expA/cases.json").read_text(encoding="utf-8"))["cases"]}
ROOT = pathlib.Path(sys.argv[1]).resolve()
GRADER = sys.argv[2] if len(sys.argv) > 2 else "sonnet"

PROMPT = """You grade a code-review report against an answer key. Judge only what the report says.

Expected verdict: {expected}
Planted problems the report should find (an id and what it is):
{planted}
Findings that must NOT be raised as blockers:
{forbidden}

Return ONLY a JSON object, no prose, with these keys:
- "verdict": "ready", "not_ready" or "unclear" - the report's own merge verdict.
- "planted": an object mapping each planted id to true if the report identifies that problem (same root cause, even if worded differently), else false.
- "false_blockers": the number of blockers in the report that are not one of the planted problems and are not real defects of the change (style, speculation, a test rewritten with equal strength, a finding already dismissed).
- "forbidden_raised": true if the report raises any of the forbidden findings as a blocker or open finding, else false.
- "evidence": one short sentence per planted id quoting where the report finds it, or "absent".

REPORT:
<<<
{report}
>>>"""


def verdict_regex(text):
    head = "\n".join(text.strip().splitlines()[:3]).lower()
    if re.search(r"not ready|não (está )?pronto|nao pronto|não pronta|not mergeable|do not merge|ainda não", head):
        return "not_ready"
    if re.search(r"\bready\b|\bpronto\b|\bpronta\b|approve", head):
        return "ready"
    return "unclear"


def grade(run):
    meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    if meta.get("exit") != 0:
        return
    out = run / f"grade-{GRADER}.json"
    if out.exists():
        return
    rep = (run / "report.md").read_text(encoding="utf-8") if (run / "report.md").exists() else ""
    c = CASES[meta["case"]]
    g = {"verdict": "unclear", "planted": {k: False for k in c["planted"]}, "false_blockers": 0,
         "forbidden_raised": False, "evidence": "empty report"}
    if rep.strip():
        prompt = PROMPT.format(expected=c["expected"],
                               planted="\n".join(f"- {k}: {v}" for k, v in c["planted"].items()) or "- (none)",
                               forbidden="\n".join(f"- {f}" for f in c["forbidden"]) or "- (none)", report=rep)
        if GRADER == "sonnet":
            cmd = [shutil.which("claude") or "claude", "-p", "--model", "sonnet", "--output-format", "json", "--tools", ""]
        else:
            cmd = [shutil.which("codex") or "codex", "exec", "-m", "gpt-6.2-sol", "-c", "model_reasoning_effort=high", "--sandbox", "read-only",
                   "--skip-git-repo-check", "--ephemeral", "-o", str(run / "grade-sol-raw.txt"), "-"]
        p = subprocess.run(cmd, cwd=W, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        try:
            txt = json.loads(p.stdout)["result"] if GRADER == "sonnet" else (run / "grade-sol-raw.txt").read_text(encoding="utf-8")
            g = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        except Exception as e:
            g["evidence"] = f"grader error: {e}: {p.stdout[:300]} {p.stderr[:300]}"
    g["verdict_regex"] = verdict_regex(rep)
    g["expected"] = c["expected"]
    g["grader"] = GRADER
    out.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    print(run.parent.name, run.name, g["verdict"], g["planted"], flush=True)


runs = [m.parent for m in ROOT.rglob("meta.json")]
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(grade, runs))
print("graded", len(runs))
