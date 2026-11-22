#!/usr/bin/env python3
"""Busca e confere literatura para a skill research. Usa só a biblioteca padrão do Python 3.11+.

Comandos:
  search "<query>" [--limit N] [--year 2020-] [--sort cited]  busca papers (OpenAlex; Semantic Scholar com S2_API_KEY)
  get <ID>                                    resolve um ID e mostra resumo e trechos; sai com 2 se não existir
  snippets "<query>" [--paper ID] [--limit N] trechos do corpo do texto (Semantic Scholar)
  verify <relatorio.md>                       confere cada [ID] "trecho" do relatório contra o registro

IDs: doi:10..., s2:<corpusId>, pmid:<n>, arxiv:<id>, openalex:W<n>.
Cada resultado mostra citações, tipo de publicação e se foi retratado.
Todo paper obtido entra no registro (--registry, padrão research/papers.jsonl); verify só aceita IDs do registro.
Saída: 0 ok; 1 verify com falha; 2 ID não existe; 3 fonte indisponível ou resposta inconclusiva; 4 argumento inválido.
Variáveis: S2_API_KEY ou SEMANTIC_API_KEY (opcional), OPENALEX_API_KEY (opcional), LIT_CORPUS (corpus local .jsonl; desliga a rede).
"""
import argparse, json, math, os, re, sys, time, unicodedata
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

UA = "lit.py/1 (research skill)"
OPENALEX, S2, CROSSREF = "https://api.openalex.org", "https://api.semanticscholar.org/graph/v1", "https://api.crossref.org"
OA_SELECT = "id,doi,title,publication_year,authorships,primary_location,abstract_inverted_index,ids,cited_by_count,type,is_retracted"
S2_FIELDS = "title,year,venue,authors,abstract,externalIds,corpusId,citationCount,publicationTypes"
KINDS = ("doi", "s2", "pmid", "arxiv", "openalex")
CITE = re.compile(r"\[\s*(?:doi|s2|pmid|arxiv|openalex|corpusid)\s*:[^\]]*\]", re.I)
BARE_DOI = re.compile(r"10\.\d{4,9}/")
ELLIPSIS = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…")
STOP = set("the and for with from that this are was were into its their our not but has have been which using use of in on to a an by as at or is be de da do das dos em para com uma um que por".split())


class NotFound(Exception):
    pass


class ApiError(Exception):
    pass


class UsageError(ValueError):
    pass


_last_call = {}


def http_json(url, headers=None, s2=False, body=None):
    if not url.startswith("https://"):
        raise UsageError(f"só HTTPS: {url}")
    host = url.split("/")[2]
    h = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    delay = 2.0
    for attempt in range(5):
        wait = _last_call.get(host, 0) + 1.1 - time.time()  # 1 req/s por fonte: limite da S2 com chave e rajada do OpenAlex
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=30) as r:  # nosec B310: URL https fixa
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url)
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                ra = e.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else delay)
                delay *= 2
                continue
            raise ApiError(f"HTTP {e.code} em {url.split('?')[0]}" + (" (limite da API; tente depois ou use a chave)" if e.code == 429 else ""))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise ApiError(f"sem conexão com {host}: {getattr(e, 'reason', e)}")
        except ValueError as e:
            raise ApiError(f"resposta inválida de {host}: {e}")


def s2_key():
    return os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_API_KEY")


def s2_headers():
    k = s2_key()
    return {"x-api-key": k} if k else {}


def oa_params(**kw):
    k = os.environ.get("OPENALEX_API_KEY")
    if k:
        kw["api_key"] = k
    return urllib.parse.urlencode(kw)


# ---------- argumentos ----------

def norm_id(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    m = re.fullmatch(r"(?i)(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s\[\]\"“”]+)", s)
    if m:
        return "doi:" + m.group(1).lower()
    m = re.fullmatch(r"(?i)(corpusid|s2|pmid|arxiv|openalex)\s*:\s*(\S+)", s)
    if m:
        kind = "s2" if m.group(1).lower() == "corpusid" else m.group(1).lower()
        v = m.group(2).upper() if kind == "openalex" else m.group(2).lower()
        pat = {"s2": r"\d+", "pmid": r"\d+", "arxiv": r"[a-z\-]*/?\d+(?:\.\d+)?(?:v\d+)?", "openalex": r"W\d+"}[kind]
        if re.fullmatch(pat, v):
            return f"{kind}:{v}"
    m = re.fullmatch(r"(?i)(?:https?://openalex\.org/)?(W\d+)", s)
    if m:
        return "openalex:" + m.group(1).upper()
    raise UsageError(f"ID não reconhecido: {s!r}. Use doi:, s2:, pmid:, arxiv: ou openalex:.")


def parse_year(spec):
    if spec is None:
        return None
    m = re.fullmatch(r"(\d{4})", spec)
    if m:
        return int(spec), int(spec)
    m = re.fullmatch(r"(\d{4})?-(\d{4})?", spec)
    if not m or not (m.group(1) or m.group(2)):
        raise UsageError(f"ano inválido: {spec!r}. Use 2021, 2020-, -2020 ou 2019-2022.")
    return (int(m.group(1)) if m.group(1) else None), (int(m.group(2)) if m.group(2) else None)


def year_ok(y, spec):
    rng = parse_year(spec) if isinstance(spec, str) else spec
    if not rng:
        return True
    if y is None:
        return False
    lo, hi = rng
    return (lo is None or int(y) >= lo) and (hi is None or int(y) <= hi)


# ---------- registros ----------

def rec(ids, title, year, authors, venue, abstract, source, snippets=(), cited_by=None, kind="", retracted=False):
    return {"id": ids[0] if ids else None, "ids": ids, "title": title or "", "year": year, "authors": list(authors)[:10],
            "venue": venue or "", "abstract": abstract or "", "snippets": list(snippets), "sources": [source],
            "cited_by": cited_by, "type": kind or "", "retracted": bool(retracted)}


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
    return rec(ids, w.get("title"), w.get("publication_year"), authors, src, " ".join(t for _, t in words), "openalex",
               cited_by=w.get("cited_by_count"), kind=w.get("type"), retracted=w.get("is_retracted"))


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
    return rec(ids, p.get("title"), p.get("year"), [a.get("name", "") for a in p.get("authors") or []], p.get("venue"),
               p.get("abstract"), "semanticscholar", cited_by=p.get("citationCount"), kind=",".join(p.get("publicationTypes") or []))


def from_crossref(m):
    year = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in m.get("author") or []]
    abstract = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.get("abstract") or "")).strip()
    return rec(["doi:" + m.get("DOI", "").lower()], (m.get("title") or [""])[0], year, authors, (m.get("container-title") or [""])[0],
               abstract, "crossref", cited_by=m.get("is-referenced-by-count"), kind=m.get("type"))


def same_paper(a, b):
    """Mesmo paper só se compartilham um ID e nenhum tipo de ID tem valores diferentes nos dois."""
    if not set(a["ids"]) & set(b["ids"]):
        return False
    for k in KINDS:
        va = {i for i in a["ids"] if i.startswith(k + ":")}
        vb = {i for i in b["ids"] if i.startswith(k + ":")}
        if va and vb and va.isdisjoint(vb):
            return False
    return True


def merge(a, b):
    for i in b["ids"]:
        if i not in a["ids"]:
            a["ids"].append(i)
    a["id"] = next((i for i in a["ids"] if i.startswith("doi:")), a["id"])
    for k in ("title", "year", "venue", "type"):
        if not a.get(k) and b.get(k):
            a[k] = b[k]
    if len(b.get("abstract") or "") > len(a.get("abstract") or ""):
        a["abstract"] = b["abstract"]
    a["authors"] = a["authors"] or b["authors"]
    a["cited_by"] = max((x for x in (a.get("cited_by"), b.get("cited_by")) if x is not None), default=None)
    a["retracted"] = bool(a.get("retracted") or b.get("retracted"))
    for k in ("snippets", "sources"):
        a.setdefault(k, [])
        for s in b.get(k) or []:
            if s not in a[k]:
                a[k].append(s)
    return a


def merge_all(records):
    out = []
    for r in records:
        hit = next((o for o in out if same_paper(o, r)), None)
        merge(hit, r) if hit else out.append(r)
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
            hit = next((o for o in self.items if same_paper(o, r)), None)
            merge(hit, r) if hit else self.items.append(json.loads(json.dumps(r)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.items), encoding="utf-8")


# ---------- corpus local (bench e uso sem rede) ----------

def tokens(t):
    return [w for w in re.findall(r"\w+", unicodedata.normalize("NFKC", t or "").lower()) if len(w) > 2 and w not in STOP]


def fields(r):
    return [r.get("title") or "", r.get("abstract") or ""] + [s.get("text", "") for s in r.get("snippets") or []]


class Corpus:
    def __init__(self, path):
        self.items = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
        self.df = {}
        for r in self.items:
            for w in set(tokens(" ".join(fields(r)))):
                self.df[w] = self.df.get(w, 0) + 1

    def score(self, q, text, title=""):
        n, tt, ti, s = len(self.items), tokens(text), tokens(title), 0.0
        for w in set(tokens(q)):
            if w in self.df:
                s += math.log(1 + n / self.df[w]) * (tt.count(w) + 2 * ti.count(w)) / (1 + 0.01 * len(tt))
        return s

    def search(self, q, limit, year, sort):
        hits = [(self.score(q, " ".join(fields(r)), r["title"]), r) for r in self.items if year_ok(r.get("year"), year)]
        hits = [h for h in sorted(hits, key=lambda x: -x[0]) if h[0] > 0][:max(limit * 3, limit)]
        if sort == "cited":
            hits.sort(key=lambda x: -(x[1].get("cited_by") or 0))
        return [r for _, r in hits][:limit]

    def get(self, cid):
        r = next((r for r in self.items if cid in r["ids"]), None)
        if not r:
            raise NotFound(cid)
        return r

    def snippets(self, q, paper, limit):
        pool = [self.get(paper)] if paper else self.items
        hits = [(self.score(q, s["text"]), r, s) for r in pool for s in r.get("snippets") or []]
        return [(r, s) for sc, r, s in sorted(hits, key=lambda x: -x[0]) if sc > 0][:limit]


# ---------- backends em rede ----------

def online_search(q, limit, year, sort):
    out, errs = [], []
    p, filters = {"per-page": limit, "select": OA_SELECT}, ["is_paratext:false"]
    rng = parse_year(year)
    if rng:
        lo, hi = rng
        filters.append("publication_year:" + (f"{lo}-{hi}" if lo and hi else f">{lo - 1}" if lo else f"<{hi + 1}"))
    if sort == "cited":
        # Ordenar a busca no texto completo por citações traz papers famosos que só mencionam o termo.
        filters.append("title_and_abstract.search:" + q.replace(",", " "))
        p["sort"] = "cited_by_count:desc"
    else:
        p["search"] = q
    p["filter"] = ",".join(filters)
    try:
        out += [from_openalex(w) for w in http_json(f"{OPENALEX}/works?{oa_params(**p)}").get("results", [])]
    except (ApiError, NotFound) as e:
        errs.append(f"OpenAlex: {e}")
    if s2_key():
        p = {"query": q, "limit": limit, "fields": S2_FIELDS, **({"year": year} if year else {})}
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
    found, errs = [], []

    def attempt(name, fn):
        try:
            found.append(fn())
        except NotFound:
            pass
        except ApiError as e:
            errs.append(f"{name}: {e}")

    if kind in ("doi", "pmid", "openalex"):
        path = v if kind == "openalex" else f"{kind}:{v}"
        attempt("OpenAlex", lambda: from_openalex(http_json(f"{OPENALEX}/works/{urllib.parse.quote(path, safe=':/')}?{oa_params(select=OA_SELECT)}")))
    if kind == "doi" and not found:
        attempt("Crossref", lambda: from_crossref(http_json(f"{CROSSREF}/works/{urllib.parse.quote(v, safe='/')}")["message"]))
    s2id = {"doi": "DOI:", "pmid": "PMID:", "s2": "CorpusId:"}.get(kind)
    if s2id and (kind == "s2" or s2_key()):
        attempt("Semantic Scholar", lambda: from_s2(http_json(f"{S2}/paper/{urllib.parse.quote(s2id + v, safe=':/')}?fields={S2_FIELDS}", s2_headers(), s2=True)))
    if found:
        for e in errs:
            print(f"aviso: {e}", file=sys.stderr)
        return merge_all(found)[0]
    if errs:  # alguma fonte não respondeu: não dá para afirmar que o ID não existe
        raise ApiError("inconclusivo: " + "; ".join(errs))
    raise NotFound(cid)


def online_snippets(q, paper, limit):
    p = {"query": q, "limit": limit}
    if paper:
        kind, v = paper.split(":", 1)
        p["paperIds"] = {"doi": "DOI:", "pmid": "PMID:", "s2": "CorpusId:", "arxiv": "ARXIV:"}.get(kind, "") + v
    out = []
    for d in http_json(f"{S2}/snippet/search?{urllib.parse.urlencode(p)}", s2_headers(), s2=True).get("data") or []:
        pp, sn = d.get("paper") or {}, d.get("snippet") or {}
        ids = [f"s2:{pp['corpusId']}"] if pp.get("corpusId") else []
        r = rec(ids, pp.get("title"), None, [a.get("name", "") if isinstance(a, dict) else str(a) for a in pp.get("authors") or []],
                None, None, "semanticscholar", [{"text": sn.get("text", ""), "section": sn.get("section") or ""}])
        out.append((r, r["snippets"][0]))
    # O snippet traz só o corpusId; sem o DOI, um trecho citado como [doi:...] não seria achado pelo verify.
    cids = list(dict.fromkeys(i for r, _ in out for i in r["ids"]))
    if cids:
        try:
            meta = http_json(f"{S2}/paper/batch?fields={S2_FIELDS}", s2_headers(), s2=True,
                             body={"ids": [i.replace("s2:", "CorpusId:") for i in cids]})
            full = {f"s2:{m.get('corpusId')}": from_s2(m) for m in meta if m}
            for r, _ in out:
                if r["ids"] and r["ids"][0] in full:
                    merge(r, full[r["ids"][0]])
        except (ApiError, NotFound) as e:
            print(f"aviso: metadados dos trechos indisponíveis ({e}); os trechos ficam só com o ID s2:", file=sys.stderr)
    return out


# ---------- verificação ----------

def norm_text(t):
    t = unicodedata.normalize("NFKC", t).translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " "}))
    return re.sub(r"\s+", " ", t).strip().lower()


def quote_in(quote, field):
    """Cada segmento entre reticências aparece, em ordem, no mesmo campo; só caixa e espaços são ignorados."""
    hay, pos = norm_text(field), 0
    for seg in ELLIPSIS.split(quote):
        seg = norm_text(seg).strip(" .,;:")
        if not seg:
            continue
        i = hay.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


def extract_quote(segment):
    """O trecho vem logo depois do [ID], com um único par de aspas no segmento até o próximo [ID]."""
    m = re.match(r"\s*[:\-–—]?\s*([\"“])", segment)
    if not m:
        return None, "sem trecho entre aspas logo depois do [ID]"
    straight, op, cl = segment.count('"'), segment.count("“"), segment.count("”")
    if m.group(1) == '"' and straight == 2 and op == cl == 0:
        a = segment.index('"')
        return segment[a + 1:segment.index('"', a + 1)], None
    if m.group(1) == "“" and op == cl == 1 and straight == 0 and segment.index("”") > segment.index("“"):
        return segment[segment.index("“") + 1:segment.index("”")], None
    return None, "aspas ambíguas: use um único par de aspas e aspas simples dentro do trecho"


def verify(path, reg, min_words):
    results = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        cites = list(CITE.finditer(line))
        rest = re.sub(r"`[^`]*`", "", CITE.sub("", line))
        if BARE_DOI.search(rest):
            results.append((n, BARE_DOI.search(rest).group(0) + "…", "DOI fora do formato [doi:...]; se não for evidência, ponha entre crases"))
        for k, c in enumerate(cites):
            seg = line[c.end():cites[k + 1].start() if k + 1 < len(cites) else len(line)]
            try:
                cid = norm_id(c.group(0))
            except UsageError:
                results.append((n, c.group(0), "ID mal formado"))
                continue
            r = reg.find(cid)
            q, why = extract_quote(seg)
            if not r:
                st = "fora do registro: o ID não foi obtido por search/get/snippets ou não existe"
            elif r.get("retracted"):
                st = "paper retratado: não vale como evidência"
            elif why:
                st = why
            elif len(re.findall(r"\w+", q)) < min_words:
                st = f"trecho curto demais (mínimo {min_words} palavras)"
            elif not any(quote_in(q, f) for f in fields(r)):
                st = "trecho não aparece no título, no resumo ou em um trecho obtido deste paper"
            else:
                st = "ok"
            results.append((n, cid, st))
    return results


# ---------- saída ----------

def show(r, full=False):
    au = ", ".join(r["authors"][:3]) + (" et al." if len(r["authors"]) > 3 else "")
    print(f"[{r['id']}] {r['title']} ({r.get('year') or 's/ ano'}) — {au or 's/ autores'}. {r.get('venue') or ''}".rstrip())
    meta = [f"citações: {r['cited_by']}" if r.get("cited_by") is not None else "citações: ?", r.get("type") or "tipo ?"]
    if r.get("retracted"):
        meta.append("RETRATADO")
    print("  " + " · ".join(meta))
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
    s = sub.add_parser("search")
    s.add_argument("query"); s.add_argument("--limit", type=int, default=10); s.add_argument("--year")
    s.add_argument("--sort", choices=["relevance", "cited"], default="relevance")
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
            parse_year(a.year)
            rs = corpus.search(a.query, a.limit, a.year, a.sort) if corpus else online_search(a.query, a.limit, a.year, a.sort)
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
    except NotFound as e:
        print(f"não encontrado: {e}")
        return 2
    except ApiError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 3
    except UsageError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
