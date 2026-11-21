"""Agrega os resultados dos experimentos A e B em CSV e gera os gráficos SVG (claro e escuro).
Uso: uv run --with matplotlib python -I bench/analyze.py <workspace> <saida-docs>
<workspace> contém expA/results e expB/results*; <saida-docs> recebe data/ e charts/."""
import csv, json, pathlib, re, statistics as st, sys
from collections import defaultdict

import matplotlib
matplotlib.use("svg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

W = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
(OUT / "data").mkdir(parents=True, exist_ok=True)
(OUT / "charts").mkdir(parents=True, exist_ok=True)
CASES = {c["id"]: c for c in json.loads((W / "expA/cases.json").read_text(encoding="utf-8"))["cases"]}

# Preço de tabela do Artificial Analysis em 20/11/2026, US$ por 1M tokens (entrada, saída). Sem desconto de cache.
PRICE = {"astra": (8, 40), "neon": (3, 15), "opus": (4, 20)}
VENDOR = {"astra": "GPT-6.2 Astra (max)", "neon": "Gemini 4 Neon (xhigh)", "opus": "Claude Opus 5.5 (max)"}


def family(arm):
    return next(k for k in PRICE if k in arm)


def tokens(meta):
    """(entrada sem cache, entrada lida do cache, saída) conforme o formato de cada CLI."""
    u, f = meta.get("usage") or {}, family(meta["arm"])
    if f == "astra":  # Codex: input_tokens já inclui cached_input_tokens
        c = u.get("cached_input_tokens", 0)
        return u.get("input_tokens", 0) - c, c, u.get("output_tokens", 0)
    if f == "neon":  # Antigravity: cache_read_tokens fica fora de input_tokens
        return u.get("input_tokens", 0), u.get("cache_read_tokens", 0), u.get("output_tokens", 0)
    return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
            u.get("output_tokens", 0))


def load_grade(run):
    gs = {}
    for g in ("sonnet", "sol"):
        p = run / f"grade-{g}.json"
        if p.exists():
            gs[g] = json.loads(p.read_text(encoding="utf-8"))
    return gs


# ---------- Experimento A ----------
rows = []
for m in sorted((W / "expA/results").rglob("meta.json")):
    meta = json.loads(m.read_text(encoding="utf-8"))
    if meta.get("exit") != 0:
        continue
    gs = load_grade(m.parent)
    if not gs:
        continue
    case = CASES[meta["case"]]
    tin, tcache, tout = tokens(meta)
    pi, po = PRICE[family(meta["arm"])]
    # Faixa de custo por preço de tabela: cache cobrado a 10% da entrada (low) ou sem desconto (high).
    low = (tin * pi + tcache * pi * 0.1 + tout * po) / 1e6
    high = ((tin + tcache) * pi + tout * po) / 1e6
    r = {"case": meta["case"], "arm": meta["arm"], "attempt": meta["attempt"], "expected": case["expected"],
         "seconds": meta["seconds"], "input_tokens": tin, "cached_input_tokens": tcache, "output_tokens": tout,
         "cost_low_usd": round(low, 4), "cost_high_usd": round(high, 4), "cost_reported_usd": meta.get("cost_usd_reported"),
         "repo_dirty": meta.get("repo_dirty"), "graders": "+".join(sorted(gs))}
    # Consenso: o veredito e cada problema plantado contam como acerto quando todos os graders concordam;
    # a discordância fica registrada em disagree.
    verdicts = {g["verdict"] for g in gs.values()}
    r["verdict"] = verdicts.pop() if len(verdicts) == 1 else "disagree"
    r["verdict_regex"] = next(iter(gs.values())).get("verdict_regex")
    r["verdict_ok"] = int(r["verdict"] == case["expected"])
    planted = list(case["planted"])
    hits = [all(g.get("planted", {}).get(k) is True for g in gs.values()) for k in planted]
    anyhit = [any(g.get("planted", {}).get(k) is True for g in gs.values()) for k in planted]
    r["planted_total"], r["planted_found"] = len(planted), sum(hits)
    r["planted_disagree"] = sum(a != b for a, b in zip(hits, anyhit))
    r["false_blockers"] = max(int(g.get("false_blockers") or 0) for g in gs.values())
    r["forbidden_raised"] = int(any(g.get("forbidden_raised") for g in gs.values()))
    rep = (m.parent / "report.md").read_text(encoding="utf-8", errors="replace")
    head = "\n".join(rep.strip().splitlines()[:5])
    # Checagem determinística do P2 de except-zera: o cabeçalho declara risco alto.
    r["risk_high_in_header"] = int(bool(re.search(r"(risco|risk)\W{0,6}\**\s*(alto|high)|high risk", head, re.I)))
    mm = re.search(r"(?:modelo|model)\W{0,4}\**\s*([^.·\n]{3,40})", head, re.I)
    r["self_reported_model"] = mm.group(1).strip(" *`") if mm else ""
    rows.append(r)

with open(OUT / "data/expA_runs.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["case"])
    w.writeheader(); w.writerows(rows)

by_arm = defaultdict(list)
for r in rows:
    by_arm[r["arm"]].append(r)
summary = []
for arm, rs in sorted(by_arm.items()):
    clean = [r for r in rs if not CASES[r["case"]]["planted"]]
    pt = sum(r["planted_total"] for r in rs)
    summary.append({
        "arm": arm, "runs": len(rs), "cases": len({r["case"] for r in rs}),
        "verdict_accuracy": round(st.mean(r["verdict_ok"] for r in rs), 3),
        "planted_recall": round(sum(r["planted_found"] for r in rs) / pt, 3) if pt else None,
        "false_blockers_per_run": round(st.mean(r["false_blockers"] for r in rs), 2),
        "clean_cases_false_alarm": round(st.mean(int(r["verdict"] != "ready" or r["forbidden_raised"]) for r in clean), 3) if clean else None,
        "median_seconds": round(st.median(r["seconds"] for r in rs)),
        "median_cost_low_usd": round(st.median(r["cost_low_usd"] for r in rs), 3),
        "median_cost_high_usd": round(st.median(r["cost_high_usd"] for r in rs), 3),
        "median_cost_reported_usd": round(st.median(r["cost_reported_usd"] for r in rs), 3) if all(r["cost_reported_usd"] for r in rs) else None,
        "median_output_tokens": round(st.median(r["output_tokens"] for r in rs)),
        "repo_dirty": sum(bool(r["repo_dirty"]) for r in rs),
        "except_zera_risk_high": f"{sum(r['risk_high_in_header'] for r in rs if r['case'] == 'except-zera')}/{sum(r['case'] == 'except-zera' for r in rs)}",
        "grader_disagreements": sum(r["verdict"] == "disagree" for r in rs) + sum(r["planted_disagree"] for r in rs),
    })
with open(OUT / "data/expA_summary.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0]))
    w.writeheader(); w.writerows(summary)

# ---------- Experimento B ----------
B_SETS = {"Claude Opus 5.5 (Claude Code)": W / "expB/results", "Gemini 4 Neon (Antigravity)": W / "expB/results-agy-ptbr"}
brows = []
for agent, root in B_SETS.items():
    for m in sorted(root.rglob("meta.json")):
        meta = json.loads(m.read_text(encoding="utf-8"))
        g = m.parent / "grade.json"
        if meta.get("exit") != 0 or not g.exists():
            continue
        crit = json.loads(g.read_text(encoding="utf-8"))
        brows.append({"agent": agent, "case": meta["case"], "arm": meta["arm"], "attempt": meta["attempt"],
                      "passed": sum(crit.values()), "total": len(crit), "seconds": meta.get("seconds"),
                      "cost_usd": meta.get("cost_usd"), "failed": ";".join(k for k, v in crit.items() if not v)})
with open(OUT / "data/expB_runs.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(brows[0]))
    w.writeheader(); w.writerows(brows)

# ---------- Gráficos ----------
THEMES = {
    "light": dict(bg="#fcfcfb", fg="#0b0b0b", fg2="#52514e", grid="#e4e3df",
                  c={"astra": "#2a78d6", "neon": "#eb6834", "opus": "#1baf7a", "with": "#2a78d6", "without": "#eda100"}),
    "dark": dict(bg="#1a1a19", fg="#f0efec", fg2="#c3c2b7", grid="#34332f",
                 c={"astra": "#3987e5", "neon": "#d95926", "opus": "#199e70", "with": "#3987e5", "without": "#c98500"}),
}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"})


def style(ax, t):
    ax.set_facecolor(t["bg"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["fg2"], length=0)
    ax.xaxis.grid(True, color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def label(arm):
    f = family(arm)
    base = VENDOR[f].split(" (")[0]
    tag = "skill upstream" if arm.startswith("upstream") else ("skill desta versão, EN" if arm.endswith("-en") else "skill desta versão")
    return f"{base}\n{tag}"


ARM_ORDER = [a for a in ("astra-max", "neon-xhigh", "opus-max", "upstream-astra-max", "upstream-neon-xhigh",
                         "upstream-opus-max") if a in by_arm]
S = {s["arm"]: s for s in summary}

for mode, t in THEMES.items():
    # Fig 1: qualidade do revisor, small multiples.
    metrics = [("verdict_accuracy", "Veredito correto"), ("planted_recall", "Problemas plantados achados"),
               ("clean_cases_false_alarm", "Alarme falso em caso limpo\n(menor é melhor)")]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 0.55 * len(ARM_ORDER) + 1.6), sharey=True, facecolor=t["bg"])
    ys = list(range(len(ARM_ORDER)))[::-1]
    for ax, (k, title) in zip(axes, metrics):
        style(ax, t)
        for y, arm in zip(ys, ARM_ORDER):
            v = S[arm][k]
            if v is None:
                continue
            ax.barh(y, v, height=0.62, color=t["c"][family(arm)], hatch="///" if arm.startswith("upstream") else None,
                    edgecolor=t["bg"], linewidth=0)
            ax.text(v + 0.02, y, f"{v:.0%}", va="center", color=t["fg"], fontsize=9)
        ax.set_xlim(0, 1.18); ax.set_xticks([0, .5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
        ax.set_title(title, color=t["fg"], fontsize=10, loc="left")
    axes[0].set_yticks(ys); axes[0].set_yticklabels([label(a) for a in ARM_ORDER], color=t["fg"], fontsize=8.5)
    n = ", ".join(f"{S[a]['runs']}" for a in ARM_ORDER)
    fig.suptitle("Experimento A: qualidade da revisão por modelo e skill", color=t["fg"], x=0.01, ha="left", fontsize=12, weight="bold")
    fig.text(0.01, 0.005, f"Execuções por braço: {n}. Hachurado = skill review do upstream. Grader cego; acerto exige consenso dos graders.",
             color=t["fg2"], fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(OUT / f"charts/revisor-qualidade-{mode}.svg", facecolor=t["bg"]); plt.close(fig)

    # Fig 2: custo e tempo contra recall.
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), facecolor=t["bg"])
    for ax, (k, xl) in zip(axes, [("median_cost_low_usd", "Custo por revisão, mediana (US$; linha: cache a 10% até sem desconto)"),
                                  ("median_seconds", "Tempo por revisão, mediana (s)")]):
        style(ax, t); ax.yaxis.grid(True, color=t["grid"], linewidth=0.8)
        for arm in ARM_ORDER:
            s = S[arm]
            if s["planted_recall"] is None:
                continue
            up = arm.startswith("upstream")
            if k == "median_cost_low_usd":
                ax.plot([s["median_cost_low_usd"], s["median_cost_high_usd"]], [s["planted_recall"]] * 2,
                        color=t["c"][family(arm)], linewidth=2, alpha=0.5, zorder=2)
            ax.scatter(s[k], s["planted_recall"], s=90, marker="s" if up else "o", zorder=3,
                       facecolor=t["bg"] if up else t["c"][family(arm)], edgecolor=t["c"][family(arm)], linewidth=2)
            ax.annotate(VENDOR[family(arm)].split(" (")[0].replace("Claude ", "").replace("Gemini 4 ", "").replace("GPT-6.2 ", "")
                        + (" (upstream)" if up else ""), (s[k], s["planted_recall"]), xytext=(7, 4),
                        textcoords="offset points", color=t["fg"], fontsize=8.5)
        ax.set_xlabel(xl, color=t["fg2"]); ax.set_ylim(0, 1.08)
        ax.set_yticks([0, .5, 1]); ax.set_yticklabels(["0%", "50%", "100%"])
    axes[0].set_ylabel("Problemas plantados achados", color=t["fg2"])
    axes[0].legend(handles=[Patch(color=t["c"][f], label=VENDOR[f]) for f in ("astra", "neon", "opus")],
                   loc="lower right", frameon=False, labelcolor=t["fg"], fontsize=8)
    fig.suptitle("Experimento A: custo e tempo contra recall (cheio = skill desta versão, vazado = upstream)",
                 color=t["fg"], x=0.01, ha="left", fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / f"charts/revisor-custo-{mode}.svg", facecolor=t["bg"]); plt.close(fig)

    # Fig 3: skill contra sem skill (experimento B), dumbbell por caso e agente.
    agg = defaultdict(list)
    for r in brows:
        agg[(r["agent"], r["case"], r["arm"])].append(r["passed"] / r["total"])
    keys = sorted({(a, c) for a, c, _ in agg})
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(keys) + 1.5), facecolor=t["bg"]); style(ax, t)
    for i, (a, c) in enumerate(keys[::-1]):
        wv, wo = agg.get((a, c, "with")), agg.get((a, c, "without"))
        if wv and wo:
            ax.plot([st.mean(wo), st.mean(wv)], [i, i], color=t["grid"], linewidth=3, zorder=1)
        for vals, arm in ((wo, "without"), (wv, "with")):
            if vals:
                ax.scatter(st.mean(vals), i, s=80, color=t["c"][arm], zorder=3, edgecolor=t["bg"], linewidth=2)
    ax.set_yticks(range(len(keys))); ax.set_yticklabels([f"{c}\n{a.split(' (')[0]}" for a, c in keys[::-1]], color=t["fg"], fontsize=8.5)
    ax.set_xlim(0, 1.05); ax.set_xticks([0, .25, .5, .75, 1]); ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Critérios determinísticos cumpridos (média das tentativas)", color=t["fg2"])
    ax.legend(handles=[Patch(color=t["c"]["with"], label="com a skill"), Patch(color=t["c"]["without"], label="mesmo pedido, sem skill")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, labelcolor=t["fg"], fontsize=9)
    fig.suptitle("Experimento B: o fluxo com e sem as skills", color=t["fg"], x=0.01, ha="left", fontsize=12, weight="bold", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / f"charts/skill-vs-sem-skill-{mode}.svg", facecolor=t["bg"]); plt.close(fig)

print(json.dumps(summary, indent=1, ensure_ascii=False))
print(len(rows), "runs A;", len(brows), "runs B")
