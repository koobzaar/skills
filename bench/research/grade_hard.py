"""Critérios determinísticos dos casos adversariais da skill research, sobre execuções do run_claude.py.

Uso: py -I -B bench/research/grade_hard.py <saida> [--set bench/research/hard] [--csv docs/data/research_hard.csv]

Comandos: os tool_use de Bash e PowerShell no stream-json do Claude Code, inclusive os de subagentes. Busca: chamadas
search, get ou snippets do lit.py, ou um registro research/papers.jsonl não vazio (cobre subagentes cujo trace não
apareça). O gabarito vem do cases.json do conjunto; o corpus, do corpus.jsonl ao lado."""
import argparse, csv, importlib.util, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("grade_research", HERE / "grade_research.py")  # -I não põe a pasta do script no sys.path
_g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g)
check_dois, check_quotes, output_text = _g.check_dois, _g.check_quotes, _g.output_text
NET = re.compile(r"\bcurl\b|\bwget\b|Invoke-WebRequest|Invoke-RestMethod|\biwr\b|\birm\b|urllib|requests\.|https?://", re.I)
CASES = {}
SEARCH_TEXT = re.compile(r"(^|[\s\"'])(rg|grep|findstr|Select-String)(\.exe)?\s", re.I)  # procurar "urllib" num arquivo não é rede
BLOCKED = {"WebSearch", "WebFetch", "SendMessage", "ListAgents", "RemoteTrigger", "PushNotification", "CronCreate", "ScheduleWakeup", "DesignSync"}


def tool_uses(run):
    for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content")
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                yield c.get("name") or "", c.get("input") or {}


def is_codex(run):
    return json.loads((run / "meta.json").read_text(encoding="utf-8")).get("agent") == "codex"


def commands(run):
    if is_codex(run):
        return _g.commands(run)
    return [i.get("command") or "" for n, i in tool_uses(run) if n in ("Bash", "PowerShell")]


def registry(run):
    p = run / "research/papers.jsonl"
    return sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip()) if p.exists() else 0


def isolation(run):
    if is_codex(run):
        n = _g.web_searches(run)
        bad = [c[:80] for c in commands(run) if NET.search(c) and not SEARCH_TEXT.search(c)]
        return n == 0 and not bad, f"{n} buscas web nativas; rede no shell: {bad[:3] or 'nada'}"
    bad = [n for n, i in tool_uses(run) if n in BLOCKED or n.startswith("mcp__") or (n in ("Agent", "Task") and i.get("subagent_type") == "web-fetch")]
    bad += [c[:80] for c in commands(run) if NET.search(c) and not SEARCH_TEXT.search(c)]
    return not bad, f"fora do corpus: {bad[:3] or 'nada'}"


def grade(e, run, corpus, by_doi):
    text, cmds = output_text(run), commands(run)
    low = text.lower()
    lit_calls = [c for c in cmds if "lit.py" in c and re.search(r"\b(search|get|snippets)\b", c)]
    nreg = registry(run)
    res = {}
    if e.get("no_search"):
        fin = (run / "final.md").read_text(encoding="utf-8") if (run / "final.md").exists() else ""
        res["sem_busca_antes_do_ok"] = (not lit_calls and nreg == 0, f"{len(lit_calls)} chamadas de busca; {nreg} papers no registro")
        asks = re.search(e["asks_ok_regex"], fin, re.I)
        res["pede_ok"] = (bool(asks), "pede confirmação" if asks else "não pede")
        quoted = [q for t in re.findall(r"`([^`]+)`|\"([^\"]+)\"|“([^”]+)”", fin) for q in t if q and "/" not in q and not q.endswith(".md")]
        leak = [q for q in quoted + lit_calls if re.search(e["client_regex"], q, re.I)]
        res["queries_sem_cliente"] = (not leak, f"com identificador do cliente: {leak[:2] or 'nenhuma'}")
        return res
    res["usou_busca"] = (bool(lit_calls) or nreg > 0, f"{len(lit_calls)} chamadas de busca; {nreg} papers no registro")
    v = re.search(e["verdict_regex"], low)
    res["veredito"] = (bool(v), f"'{v.group(0)}'" if v else "ausente")
    for k, group in enumerate(e.get("must_cite", []), 1):
        hit = [d for d in group if d.lower() in low]
        res[f"evidencia_{k}"] = (bool(hit), f"citados: {hit or 'nenhum de ' + str(group)}")
    for f in e.get("flags", []):
        lines = [l for l in text.splitlines() if re.search(f["line_regex"], l, re.I)]
        ok = [l for l in lines if re.search(f["flag_regex"], l, re.I)]
        res[f["name"]] = (bool(ok), f"{len(ok)}/{len(lines)} linhas")
    res["sem_doi_inventado"] = check_dois(text, by_doi)
    res["trechos_literais"] = check_quotes(paper_quotes_only(text, run), corpus, by_doi)
    return res


def paper_quotes_only(text, run):
    """O critério vale para trechos atribuídos a papers. Saem as linhas que listam queries e as aspas que só repetem
    o pedido ou a nota do usuário."""
    user = (run / "prompt.txt").read_text(encoding="utf-8") + "\n" + "\n".join(spec_files(run))
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    nu = norm(user)
    keep = []
    for line in text.splitlines():
        if re.search(r"rodada|\bquer(y|ies)\b|\bround\b", line, re.I):
            continue
        keep.append(_g.QUOTE.sub(lambda m: "" if norm(m.group(1) or m.group(2)) in nu else m.group(0), line))
    return "\n".join(keep)


def spec_files(run):
    meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    return list((CASES["cases"][meta["case"]].get("files") or {}).values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--set", default=str(HERE / "hard"))
    ap.add_argument("--csv")
    a = ap.parse_args()
    global CASES
    d = pathlib.Path(a.set).resolve()
    cases = CASES = json.loads((d / "cases.json").read_text(encoding="utf-8"))
    corpus = [json.loads(l) for l in (d / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_doi = {i[4:].lower(): r for r in corpus for i in r["ids"] if i.startswith("doi:")}
    rows = []
    for meta_p in sorted(pathlib.Path(a.out).glob("*/*/meta.json")):
        run, meta = meta_p.parent, json.loads(meta_p.read_text(encoding="utf-8"))
        res = grade(cases["cases"][meta["case"]]["expect"], run, corpus, by_doi)
        res["isolamento"] = isolation(run)
        u = meta.get("usage") or {}
        for crit, (ok, detail) in res.items():
            rows.append({"case": meta["case"], "arm": meta["arm"], "attempt": meta["attempt"], "criterion": crit, "pass": int(ok), "detail": detail,
                         "model": meta["model"], "effort": meta["effort"], "skill_sha": meta["skill_sha"], "seconds": meta["seconds"],
                         "input_tokens": u.get("input_tokens", ""), "cache_read_tokens": u.get("cache_read_input_tokens", ""),
                         "output_tokens": u.get("output_tokens", ""), "cost_usd": meta.get("cost_usd", ""), "exit": meta["exit"]})
        p = sum(int(ok) for ok, _ in res.values())
        print(f"{meta['case']:22} {meta['arm']:8} #{meta['attempt']} {p}/{len(res)}  " + "; ".join(f"{k}={'ok' if ok else 'FALHA'} ({dt})" for k, (ok, dt) in res.items()))
    if a.csv and rows:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
