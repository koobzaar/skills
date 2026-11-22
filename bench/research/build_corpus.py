"""Monta o corpus local do bench da skill research.

Uso:
  py -I -B bench/research/build_corpus.py --discover   # roda as queries de cases.json e grava corpus_ids.txt
  py -I -B bench/research/build_corpus.py              # refaz o corpus a partir de corpus_ids.txt, em lotes
  --set bench/research/hard                             # usa o cases.json, corpus_ids.txt e corpus.jsonl de outra pasta

Precisa de rede e, para trechos e resumos da Elsevier, de S2_API_KEY ou SEMANTIC_API_KEY. O corpus (resumos e
trechos) fica em bench/research/corpus.jsonl, fora do Git; a lista de IDs fica versionada."""
import argparse, importlib.util, json, pathlib, sys, urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("lit", HERE.parents[1] / "skills/research/lit.py")
lit = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(lit)
CASES, IDS, OUT = None, None, None


def use_set(d):
    global CASES, IDS, OUT
    CASES = json.loads((d / "cases.json").read_text(encoding="utf-8"))
    IDS, OUT = d / "corpus_ids.txt", d / "corpus.jsonl"


def required_dois():
    out = set(CASES["corpus"].get("required_dois", []))
    for c in CASES["cases"].values():
        e = c["expect"]
        out.update(e.get("required_any", []))
        if e.get("distorted_doi"):
            out.add(e["distorted_doi"])
    return sorted(out | set(CASES["corpus"]["snippet_queries"]))


def discover():
    recs = []
    for q in CASES["corpus"]["queries"]:
        rs = lit.online_search(q, 15, None, "relevance")
        print(f"{len(rs):>3} {q}", flush=True)
        recs += rs
    have = {i for r in recs for i in r["ids"]}
    for d in required_dois():
        if "doi:" + d.lower() not in have:
            recs.append(lit.online_get("doi:" + d))
    recs = lit.merge_all(recs)
    ids = [next((i for i in r["ids"] if i.startswith("doi:")), r["ids"][0]) for r in recs if r["ids"]]
    IDS.write_text("".join(i + "\n" for i in sorted(set(ids))), encoding="utf-8")
    return recs


def rebuild():
    ids = [l.strip() for l in IDS.read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = []
    dois = [i[4:] for i in ids if i.startswith("doi:")]
    for k in range(0, len(dois), 50):  # filtro OR do OpenAlex aceita até 50 valores
        p = lit.oa_params(filter="doi:" + "|".join(dois[k:k + 50]), select=lit.OA_SELECT, **{"per-page": 50})
        recs += [lit.from_openalex(w) for w in lit.http_json(f"{lit.OPENALEX}/works?{p}").get("results", [])]
    others = [i for i in ids if not i.startswith("doi:")]
    for i in others:
        recs.append(lit.online_get(i))
    if lit.s2_key():
        s2ids = [("DOI:" + i[4:]) if i.startswith("doi:") else i.replace("s2:", "CorpusId:") for i in ids if i.split(":")[0] in ("doi", "s2")]
        for k in range(0, len(s2ids), 500):
            meta = lit.http_json(f"{lit.S2}/paper/batch?fields={lit.S2_FIELDS}", lit.s2_headers(), s2=True, body={"ids": s2ids[k:k + 500]})
            recs += [lit.from_s2(m) for m in meta if m]
    return lit.merge_all(recs)


def add_snippets(recs):
    if not lit.s2_key():
        print("aviso: sem chave da Semantic Scholar; o corpus fica sem trechos do corpo do texto", file=sys.stderr)
        return recs
    for doi, q in CASES["corpus"]["snippet_queries"].items():
        try:
            hits = lit.online_snippets(q, "doi:" + doi, 5)
        except lit.ApiError as e:
            print(f"aviso: trechos de {doi} indisponíveis: {e}", file=sys.stderr)
            continue
        print(f"{len(hits):>3} trechos {doi}", flush=True)
        recs += [r for r, _ in hits]
    return lit.merge_all(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--set", default=str(HERE), help="pasta com cases.json; o corpus é gravado nela")
    a = ap.parse_args()
    use_set(pathlib.Path(a.set).resolve())
    recs = add_snippets(discover() if a.discover else rebuild())
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    missing = [d for d in required_dois() if not any("doi:" + d.lower() in r["ids"] for r in recs)]
    print(f"{len(recs)} papers em {OUT.name}; DOIs do gabarito ausentes: {missing or 'nenhum'}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
