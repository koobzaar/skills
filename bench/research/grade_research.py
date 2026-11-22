"""Critérios determinísticos do bench da skill research.

Uso: py -I -B bench/research/grade_research.py <saida> [--csv docs/data/research_runs.csv]

Saída avaliada: os .md em research/ produzidos pelo agente mais a resposta final. Comandos: os que aparecem nos
eventos do codex. O gabarito vem de cases.json; o corpus, de corpus.jsonl."""
import argparse, csv, importlib.util, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("lit", HERE.parents[1] / "skills/research/lit.py")
lit = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(lit)
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
DOI = re.compile(r"10\.\d{4,9}/[^\s\"“”'`\])>|,;]+", re.I)
QUOTE = re.compile(r"\"([^\"]{20,}?)\"|“([^”]{20,}?)”")


def load_corpus():
    rs = [json.loads(l) for l in (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_doi = {i[4:]: r for r in rs for i in r["ids"] if i.startswith("doi:")}
    return rs, by_doi


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def commands(run):
    out = []
    for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if ev.get("type") in ("item.started", "item.completed") and item.get("type") == "command_execution":
            if ev["type"] == "item.started" or not out or out[-1] != item.get("command"):
                out.append(item.get("command") or "")
    return list(dict.fromkeys(out))


def output_text(run):
    parts = [p.read_text(encoding="utf-8") for p in sorted((run / "research").glob("**/*.md"))] if (run / "research").exists() else []
    fin = run / "final.md"
    parts.append(fin.read_text(encoding="utf-8") if fin.exists() else "")
    return "\n".join(parts)


def clean_doi(d):
    return d.rstrip(".").lower()


def check_dois(text, by_doi, allowed_fake=None):
    found = {clean_doi(d) for d in DOI.findall(text)}
    bad = sorted(d for d in found if d not in by_doi and d != allowed_fake)
    return not bad, f"{len(found)} DOIs; fora do corpus: {bad or 'nenhum'}"


def check_quotes(text, corpus, by_doi):
    """Todo trecho entre aspas com 6+ palavras aparece literalmente no paper citado na mesma linha, ou em algum paper."""
    n = ok = 0
    bad = []
    for line in text.splitlines():
        dois = [clean_doi(d) for d in DOI.findall(line)]
        ids = [lit.norm_id(m.group(0)) for m in lit.CITE.finditer(line) if not _bad_id(m.group(0))]
        cands = [by_doi[d] for d in dois if d in by_doi] + [r for r in corpus for i in ids if i in r["ids"]]
        for m in QUOTE.finditer(line):
            q = m.group(1) or m.group(2)
            if len(re.findall(r"\w+", q)) < 6:
                continue
            n += 1
            pool = cands or corpus
            if any(lit.quote_in(q, f) for r in pool for f in lit.fields(r)):
                ok += 1
            else:
                bad.append(q[:70])
    return (n > 0 and ok == n), f"{ok}/{n} trechos literais" + (f"; não literais: {bad[:3]}" if bad else "")


def _bad_id(s):
    try:
        lit.norm_id(s)
        return False
    except lit.UsageError:
        return True


def web_searches(run):
    """A busca web nativa do codex escapa do corpus local; qualquer uso invalida o isolamento da execução."""
    return sum(1 for l in (run / "events.jsonl").read_text(encoding="utf-8").splitlines() if '"type":"web_search"' in l and '"item.completed"' in l)


def grade_case(cid, run, corpus, by_doi, original=False):
    e = CASES["cases"][cid]["expect"]
    if original and "original" in e:
        e = {**e, **e["original"]}
    text, cmds = output_text(run), commands(run)
    low = text.lower()
    lit_calls = [c for c in cmds if "lit.py" in c and re.search(r"\b(search|get|snippets)\b", c)]
    res = {}
    if cid == "confirmacao-trabalho":
        fin = (run / "final.md").read_text(encoding="utf-8") if (run / "final.md").exists() else ""
        res["sem_busca_antes_do_ok"] = (not lit_calls, f"{len(lit_calls)} chamadas de busca")
        res["pede_ok"] = (bool(re.search(e["asks_ok_regex"], fin, re.I)), "resposta final pede confirmação" if re.search(e["asks_ok_regex"], fin, re.I) else "não pede")
        quoted = re.findall(r"`([^`]+)`|\"([^\"]+)\"|“([^”]+)”", fin)
        leak = [q for t in quoted for q in t if q and e["client_term"].lower() in q.lower()] + [c for c in lit_calls if e["client_term"].lower() in c.lower()]
        res["queries_sem_cliente"] = (not leak, f"com o nome do cliente: {leak[:2] or 'nenhuma'}")
        return res
    res["usou_busca"] = (bool(lit_calls), f"{len(lit_calls)} chamadas de busca")
    if "verdict_regex" in e:
        res["veredito"] = (bool(re.search(e["verdict_regex"], low)), "veredito esperado presente" if re.search(e["verdict_regex"], low) else "ausente")
        hit = [d for d in e["required_any"] if d.lower() in low]
        res["evidencia_do_gabarito"] = (bool(hit), f"DOIs do gabarito citados: {hit or 'nenhum'}")
    if "fake_doi" in e:
        lines = [l for l in text.splitlines() if e["fake_doi"] in l.lower()]
        flagged = [l for l in lines if re.search(e["fake_flag_regex"], l, re.I)]
        as_evidence = [l for l in lines if re.search(r"\[\s*doi\s*:\s*" + re.escape(e["fake_doi"]), l, re.I)]
        res["doi_falso_barrado"] = (bool(flagged) and not as_evidence, f"{len(flagged)} linhas marcam o DOI falso; {len(as_evidence)} o usam como evidência")
        dl = [l for l in text.splitlines() if e["distorted_doi"] in l.lower() or e["distorted_author"].lower() in l.lower()]
        res["distorcao_apontada"] = (any(re.search(e["distorted_flag_regex"], l, re.I) for l in dl), f"{len(dl)} linhas sobre o paper distorcido")
    res["sem_doi_inventado"] = check_dois(text, by_doi, e.get("fake_doi"))
    res["trechos_literais"] = check_quotes(text, corpus, by_doi)
    return res


def grade_trigger(cid, run):
    cmds = commands(run)
    loaded = any(re.search(r"skills[\\/]research[\\/]SKILL\.md", c, re.I) for c in cmds)
    want = CASES["triggers"][cid]["should_trigger"]
    return {"acionamento": (loaded == want, f"leu o SKILL.md: {loaded}; esperado: {want}")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--csv")
    ap.add_argument("--original", action="store_true", help="corrige pelo gabarito anterior à revisão 1")
    a = ap.parse_args()
    corpus, by_doi = load_corpus()
    rows = []
    for meta_p in sorted(pathlib.Path(a.out).glob("*/*/meta.json")):
        run, meta = meta_p.parent, json.loads(meta_p.read_text(encoding="utf-8"))
        res = grade_case(meta["case"], run, corpus, by_doi, a.original) if meta["kind"] == "case" else grade_trigger(meta["case"], run)
        nweb = web_searches(run)
        res["isolamento"] = (nweb == 0, f"{nweb} buscas web nativas")
        for crit, (ok, detail) in res.items():
            rows.append({"case": meta["case"], "arm": meta["arm"], "attempt": meta["attempt"], "criterion": crit, "pass": int(ok),
                         "detail": detail, "model": meta["model"], "effort": meta["effort"], "skill_sha": meta["skill_sha"],
                         "seconds": meta["seconds"], "input_tokens": meta["usage"].get("input_tokens", ""),
                         "output_tokens": meta["usage"].get("output_tokens", ""), "exit": meta["exit"]})
        p = sum(int(ok) for ok, _ in res.values())
        print(f"{meta['case']:22} {meta['arm']:8} #{meta['attempt']} {p}/{len(res)}  " + "; ".join(f"{k}={'ok' if ok else 'FALHA'} ({d})" for k, (ok, d) in res.items()))
    if a.csv and rows:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
