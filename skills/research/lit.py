#!/usr/bin/env python3
"""Busca e confere literatura para a skill research. Usa só a biblioteca padrão do Python 3.11+.

Comandos:
  search "<query>" [--limit N] [--year 2020-]   busca papers (OpenAlex; Semantic Scholar se houver S2_API_KEY)
  get <ID>                                      resolve um ID e mostra resumo e trechos; sai com 2 se não existir
  snippets "<query>" [--paper ID] [--limit N]   trechos do corpo do texto (Semantic Scholar)
  verify <relatorio.md>                         confere cada [ID] "trecho" do relatório contra o registro

IDs: doi:10..., s2:<corpusId>, pmid:<n>, arxiv:<id>, openalex:W<n>.
Todo paper obtido entra no registro (--registry, padrão research/papers.jsonl); verify só aceita IDs do registro.
Variáveis: S2_API_KEY (opcional), OPENALEX_API_KEY (opcional), LIT_CORPUS (corpus local .jsonl; desliga a rede).
"""
import argparse, json, math, os, re, sys, time, unicodedata
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

UA = "lit.py/1 (research skill)"
OPENALEX, S2, CROSSREF = "https://api.openalex.org", "https://api.semanticscholar.org/graph/v1", "https://api.crossref.org"
OA_SELECT = "id,doi,title,publication_year,authorships,primary_location,abstract_inverted_index,ids"
S2_FIELDS = "title,year,venue,authors,abstract,externalIds,corpusId"
CITE = re.compile(r"\[((?:doi|s2|pmid|arxiv|openalex):[^\]\s]+)\]", re.I)
QUOTE = re.compile(r"[\"“]([^\"“”]{3,}?)[\"”]")
STOP = set("the and for with from that this are was were into its their our not but has have been which using use of in on to a an by as at or is be de da do das dos em para com uma um que por".split())


class NotFound(Exception):
    pass


class ApiError(Exception):
    pass


_last_s2 = [0.0]


def http_json(url, headers=None, s2=False):
    h = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    delay = 2.0
    for attempt in range(5):
        if s2:  # com chave, o limite é 1 req/s
            wait = _last_s2[0] + 1.1 - time.time()
            if wait > 0:
                time.sleep(wait)
            _last_s2[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url)
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                ra = e.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else delay)
                delay *= 2
                continue
            raise ApiError(f"HTTP {e.code} em {url.split('?')[0]}" + (" (limite da API; tente depois ou use S2_API_KEY)" if e.code == 429 else ""))
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise ApiError(f"sem conexão com {url.split('/')[2]}: {e.reason}")


def s2_headers():
    k = os.environ.get("S2_API_KEY")
    return {"x-api-key": k} if k else {}


def oa_params(**kw):
    k = os.environ.get("OPENALEX_API_KEY")
    if k:
        kw["api_key"] = k
    return urllib.parse.urlencode(kw)


# ---------- IDs e registros ----------

def norm_id(s):
    s = s.strip().strip("[]")
    m = re.match(r"(?i)^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", s)
    if m:
        return "doi:" + m.group(1).lower()
    low = s.lower()
    for p, k in (("corpusid:", "s2"), ("s2:", "s2"), ("pmid:", "pmid"), ("arxiv:", "arxiv"), ("openalex:", "openalex")):
        if low.startswith(p):
            v = s[len(p):].strip()
            return f"{k}:{v.upper() if k == 'openalex' else v.lower() if k == 'arxiv' else v}"
    m = re.match(r"(?i)^(?:https?://openalex\.org/)?(W\d+)$", s)
    if m:
        return "openalex:" + m.group(1).upper()
    raise SystemExit(f"ID não reconhecido: {s}. Use doi:, s2:, pmid:, arxiv: ou openalex:.")


def rec(ids, title, year, authors, venue, abstract, source, snippets=()):
    return {"id": ids[0] if ids else None, "ids": ids, "title": title or "", "year": year, "authors": list(authors)[:10],
            "venue": venue or "", "abstract": abstract or "", "snippets": list(snippets), "sources": [source]}


def from_openalex(w):
    ids = []
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    if doi:
        ids.append("doi:" + doi.lower())
    oid = (w.get("id") or "").rsplit("/", 1)[-1]
    if oid:
        ids.append("openalex:" + oid)
    pm = ((w.get("ids") or {}).get("pmid") or "").rsplit("/", 1)[-1]
    if pm:
        ids.append("pmid:" + pm)
    inv = w.get("abstract_inverted_index") or {}
    words = sorted((p, t) for t, ps in inv.items() for p in ps)
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
    authors = [(a.get("author") or {}).get("display_name", "") for a in w.get("authorships") or []]
    return rec(ids, w.get("title"), w.get("publication_year"), authors, src, " ".join(t for _, t in words), "openalex")


def from_s2(p):
    ex = p.get("externalIds") or {}
    ids = []
    if ex.get("DOI"):
        ids.append("doi:" + ex["DOI"].lower())
    cid = p.get("corpusId") or ex.get("CorpusId")
    if cid:
        ids.append(f"s2:{cid}")
    if ex.get("PubMed"):
        ids.append("pmid:" + str(ex["PubMed"]))
    if ex.get("ArXiv"):
        ids.append("arxiv:" + ex["ArXiv"].lower())
    return rec(ids, p.get("title"), p.get("year"), [a.get("name", "") for a in p.get("authors") or []],
               p.get("venue"), p.get("abstract"), "semanticscholar")


def from_crossref(m):
    doi = m.get("DOI", "").lower()
    year = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in m.get("author") or []]
    abstract = re.sub(r"<[^>]+>", " ", m.get("abstract") or "")
    return rec(["doi:" + doi], (m.get("title") or [""])[0], year, authors, (m.get("container-title") or [""])[0],
               re.sub(r"\s+", " ", abstract).strip(), "crossref")


def merge(a, b):
    for i in b["ids"]:
        if i not in a["ids"]:
            a["ids"].append(i)
    doi = next((i for i in a["ids"] if i.startswith("doi:")), None)
    a["id"] = doi or a["id"]
    for k in ("title", "year", "venue", "abstract"):
        if not a.get(k) and b.get(k):
            a[k] = b[k]
    if len(b.get("abstract") or "") > len(a.get("abstract") or ""):
        a["abstract"] = b["abstract"]
    if not a["authors"]:
        a["authors"] = b["authors"]
    for s in b.get("snippets") or []:
        if s not in a["snippets"]:
            a["snippets"].append(s)
    for s in b.get("sources") or []:
        if s not in a["sources"]:
            a["sources"].append(s)
    return a


def merge_all(records):
    out = []
    for r in records:
        hit = next((o for o in out if set(o["ids"]) & set(r["ids"])), None)
        if hit:
            merge(hit, r)
        else:
            out.append(r)
    return out


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.items = []
        if self.path.exists():
            self.items = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def find(self, cid):
        return next((r for r in self.items if cid in r["ids"]), None)

    def add(self, records):
        for r in records:
            hit = next((o for o in self.items if set(o["ids"]) & set(r["ids"])), None)
            if hit:
                merge(hit, r)
            else:
                self.items.append(json.loads(json.dumps(r)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.items), encoding="utf-8")


# ---------- corpus local (bench e uso sem rede) ----------

def tokens(t):
    return [w for w in re.findall(r"\w+", unicodedata.normalize("NFKC", t or "").lower()) if len(w) > 2 and w not in STOP]


class Corpus:
    def __init__(self, path):
        self.items = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
        self.df = {}
        for r in self.items:
            for w in set(tokens(full_text(r))):
                self.df[w] = self.df.get(w, 0) + 1

    def score(self, q, text, title=""):
        n = len(self.items)
        tt, ti = tokens(text), tokens(title)
        s = 0.0
        for w in set(tokens(q)):
            if w in self.df:
                s += math.log(1 + n / self.df[w]) * (tt.count(w) + 2 * ti.count(w)) / (1 + 0.01 * len(tt))
        return s

    def search(self, q, limit, year):
        hits = [(self.score(q, full_text(r), r["title"]), r) for r in self.items if year_ok(r.get("year"), year)]
        return [r for s, r in sorted(hits, key=lambda x: -x[0]) if s > 0][:limit]

    def get(self, cid):
        r = next((r for r in self.items if cid in r["ids"]), None)
        if not r:
            raise NotFound(cid)
        return r

    def snippets(self, q, paper, limit):
        pool = [self.get(paper)] if paper else self.items
        hits = [(self.score(q, s["text"]), r, s) for r in pool for s in r.get("snippets") or []]
        return [(r, s) for sc, r, s in sorted(hits, key=lambda x: -x[0]) if sc > 0][:limit]


def full_text(r):
    return " ".join([r.get("title") or "", r.get("abstract") or ""] + [s["text"] for s in r.get("snippets") or []])


def year_ok(y, spec):
    if not spec:
        return True
    if y is None:
        return False
    a, _, b = spec.partition("-")
    lo = int(a) if a else -9999
    hi = (int(b) if b else 9999) if "-" in spec else lo
    return lo <= int(y) <= hi


# ---------- backends em rede ----------

def online_search(q, limit, year):
    out, errs = [], []
    p = {"search": q, "per-page": limit, "select": OA_SELECT}
    if year:
        lo, dash, hi = year.partition("-")
        f = (f">{int(lo) - 1}" if lo else "") if dash and not hi else (f"<{int(hi) + 1}" if not lo else year)
        p["filter"] = "publication_year:" + f
    try:
        out += [from_openalex(w) for w in http_json(f"{OPENALEX}/works?{oa_params(**p)}").get("results", [])]
    except (ApiError, NotFound) as e:
        errs.append(f"OpenAlex: {e}")
    if os.environ.get("S2_API_KEY"):
        p = {"query": q, "limit": limit, "fields": S2_FIELDS}
        if year:
            p["year"] = year
        try:
            out += [from_s2(x) for x in http_json(f"{S2}/paper/search?{urllib.parse.urlencode(p)}", s2_headers(), s2=True).get("data") or []]
        except (ApiError, NotFound) as e:
            errs.append(f"Semantic Scholar: {e}")
    if errs and not out:
        raise ApiError("; ".join(errs))
    for e in errs:
        print(f"aviso: {e}", file=sys.stderr)
    return merge_all(out)


def online_get(cid):
    kind, v = cid.split(":", 1)
    if kind == "arxiv":
        kind, v = "doi", f"10.48550/arxiv.{v}"
    found = []
    if kind in ("doi", "pmid", "openalex"):
        path = v if kind == "openalex" else f"{kind}:{v}"
        try:
            found.append(from_openalex(http_json(f"{OPENALEX}/works/{urllib.parse.quote(path, safe=':/')}?{oa_params(select=OA_SELECT)}")))
        except NotFound:
            pass
    if kind == "doi" and not found:
        try:
            found.append(from_crossref(http_json(f"{CROSSREF}/works/{urllib.parse.quote(v, safe='/')}")["message"]))
        except NotFound:
            pass
    if kind == "s2" or os.environ.get("S2_API_KEY"):
        s2id = {"doi": "DOI:", "pmid": "PMID:", "s2": "CorpusId:"}.get(kind)
        if s2id:
            try:
                found.append(from_s2(http_json(f"{S2}/paper/{urllib.parse.quote(s2id + v, safe=':/')}?fields={S2_FIELDS}", s2_headers(), s2=True)))
            except NotFound:
                pass
            except ApiError as e:
                if kind == "s2":
                    raise
                print(f"aviso: Semantic Scholar: {e}", file=sys.stderr)
    if not found:
        raise NotFound(cid)
    return merge_all(found)[0]


def online_snippets(q, paper, limit):
    p = {"query": q, "limit": limit}
    if paper:
        kind, v = paper.split(":", 1)
        p["paperIds"] = {"doi": "DOI:", "pmid": "PMID:", "s2": "CorpusId:", "arxiv": "ARXIV:"}.get(kind, "") + v
    data = http_json(f"{S2}/snippet/search?{urllib.parse.urlencode(p)}", s2_headers(), s2=True).get("data") or []
    out = []
    for d in data:
        pp, sn = d.get("paper") or {}, d.get("snippet") or {}
        ids = [f"s2:{pp['corpusId']}"] if pp.get("corpusId") else []
        r = rec(ids, pp.get("title"), None, [a.get("name", "") if isinstance(a, dict) else str(a) for a in pp.get("authors") or []],
                None, None, "semanticscholar", [{"text": sn.get("text", ""), "section": sn.get("section") or ""}])
        out.append((r, r["snippets"][0]))
    return out


# ---------- verificação ----------

def norm_words(t):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", t).lower()))


def quote_in(quote, text):
    hay, pos = " " + norm_words(text) + " ", 0
    segs = [norm_words(s) for s in re.split(r"\.\.\.|…|\[\.\.\.\]", quote)]
    for s in [s for s in segs if s]:
        i = hay.find(" " + s + " ", pos)
        if i < 0:
            return False
        pos = i + len(s)
    return True


def verify(path, reg, min_words):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    results = []
    for n, line in enumerate(lines, 1):
        cites, quotes = list(CITE.finditer(line)), list(QUOTE.finditer(line))
        for k, c in enumerate(cites):
            nxt = cites[k + 1].start() if k + 1 < len(cites) else len(line)
            prv = cites[k - 1].end() if k else 0
            q = next((m for m in quotes if c.end() <= m.start() < nxt), None) or \
                next((m for m in reversed(quotes) if prv <= m.start() and m.end() <= c.start()), None)
            try:
                cid = norm_id(c.group(1))
            except SystemExit:
                results.append((n, c.group(1), "ID mal formado"))
                continue
            r = reg.find(cid)
            if not r:
                results.append((n, cid, "fora do registro: o ID não foi obtido por search/get/snippets ou não existe"))
            elif not q:
                results.append((n, cid, "sem trecho entre aspas na mesma linha"))
            elif len(norm_words(q.group(1)).split()) < min_words:
                results.append((n, cid, f"trecho curto demais (mínimo {min_words} palavras)"))
            elif not quote_in(q.group(1), full_text(r)):
                results.append((n, cid, "trecho não aparece no texto obtido deste paper"))
            else:
                results.append((n, cid, "ok"))
    return results


# ---------- saída ----------

def show(r, full=False):
    au = ", ".join(r["authors"][:3]) + (" et al." if len(r["authors"]) > 3 else "")
    print(f"[{r['id']}] {r['title']} ({r.get('year') or 's/ano'}) — {au or 's/ autores'}. {r.get('venue') or ''}".rstrip())
    others = [i for i in r["ids"] if i != r["id"]]
    if others:
        print("  outros IDs: " + ", ".join(others))
    ab = r.get("abstract") or ""
    if full:
        print("  resumo: " + (ab or "(sem resumo nas fontes)"))
        for i, s in enumerate(r.get("snippets") or [], 1):
            print(f"  trecho {i} ({s.get('section') or 's/ seção'}): {s['text']}")
    else:
        print("  resumo: " + ((ab[:300] + "…") if len(ab) > 300 else ab or "(sem resumo)"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=os.environ.get("LIT_REGISTRY", "research/papers.jsonl"))
    ap.add_argument("--json", action="store_true", help="imprime registros JSON completos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=10); s.add_argument("--year")
    g = sub.add_parser("get"); g.add_argument("id")
    n = sub.add_parser("snippets"); n.add_argument("query"); n.add_argument("--paper"); n.add_argument("--limit", type=int, default=5)
    v = sub.add_parser("verify"); v.add_argument("report"); v.add_argument("--min-words", type=int, default=6)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    reg = Registry(a.registry)
    corpus = Corpus(os.environ["LIT_CORPUS"]) if os.environ.get("LIT_CORPUS") else None
    try:
        if a.cmd == "search":
            rs = corpus.search(a.query, a.limit, a.year) if corpus else online_search(a.query, a.limit, a.year)
            reg.add(rs)
            if not rs:
                print("nenhum resultado")
            for r in rs:
                print(json.dumps(r, ensure_ascii=False)) if a.json else show(r)
        elif a.cmd == "get":
            cid = norm_id(a.id)
            try:
                r = corpus.get(cid) if corpus else online_get(cid)
            except NotFound:
                print(f"não encontrado: {cid}")
                return 2
            reg.add([r])
            print(json.dumps(r, ensure_ascii=False)) if a.json else show(reg.find(cid) or r, full=True)
        elif a.cmd == "snippets":
            paper = norm_id(a.paper) if a.paper else None
            hits = corpus.snippets(a.query, paper, a.limit) if corpus else online_snippets(a.query, paper, a.limit)
            reg.add([r for r, _ in hits])
            if not hits:
                print("nenhum trecho")
            for r, sn in hits:
                print(f"[{r['id']}] {r['title']} — {sn.get('section') or 's/ seção'}\n  trecho: {sn['text']}")
        else:
            res = verify(a.report, reg, a.min_words)
            for n_, cid, st in res:
                print(f"{'OK   ' if st == 'ok' else 'FALHA'} linha {n_} [{cid}] {st}")
            bad = sum(st != "ok" for *_, st in res)
            print(f"{len(res)} citações, {bad} com falha" if res else "nenhuma citação [ID] encontrada")
            return 1 if bad or not res else 0
    except ApiError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
