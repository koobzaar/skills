"""Agrega os resultados dos experimentos A e B em CSV e gera os gráficos SVG (claro e escuro).
Uso: uv run --with matplotlib python -I bench/analyze.py <workspace> <saida-docs>
<workspace> contém expA/results e expB/results*; <saida-docs> recebe data/ e charts/.
Toda tentativa entra nas taxas e no custo, inclusive timeout e falha do CLI (exit != 0), que contam como erro: tirar as
falhas do denominador esconderia o custo e o sucesso real de cada braço. O custo também sai por sucesso."""
import csv, json, pathlib, re, statistics as st, sys
from collections import defaultdict

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


def load_cases(w):
    return {c["id"]: c for f in ("cases.json", "cases_reserva.json") if (w / "expA" / f).exists()
            for c in json.loads((w / "expA" / f).read_text(encoding="utf-8"))["cases"]}


def per_success(total, n):
    return round(total / n, 4) if n else None


# ---------- Experimento A ----------
def row_a(meta, gs, case, report):
    """Uma linha por tentativa. Tentativa com exit != 0 entra com veredito "error" e nenhum achado."""
    tin, tcache, tout = tokens(meta)
    pi, po = PRICE[family(meta["arm"])]
    # Faixa de custo por preço de tabela: cache cobrado a 10% da entrada (low) ou sem desconto (high).
    low = (tin * pi + tcache * pi * 0.1 + tout * po) / 1e6
    high = ((tin + tcache) * pi + tout * po) / 1e6
    failed = meta.get("exit") != 0
    r = {"case": meta["case"], "case_set": meta.get("case_set", "dev"), "arm": meta["arm"], "attempt": meta["attempt"],
         "expected": case["expected"], "exit": meta.get("exit"), "failed": int(failed),
         "seconds": meta["seconds"], "input_tokens": tin, "cached_input_tokens": tcache, "output_tokens": tout,
         "cost_low_usd": round(low, 4), "cost_high_usd": round(high, 4), "cost_reported_usd": meta.get("cost_usd_reported"),
         "repo_dirty": meta.get("repo_dirty"), "graders": "+".join(sorted(gs))}
    planted = list(case["planted"])
    if failed:
        r.update(verdict="error", verdict_regex="", verdict_ok=0, planted_total=len(planted), planted_found=0,
                 planted_disagree=0, false_blockers=0, forbidden_raised=0, risk_high_in_header=0, self_reported_model="")
        return r
    # Consenso: o veredito e cada problema plantado contam como acerto quando todos os graders concordam;
    # a discordância fica registrada em disagree.
    verdicts = {g["verdict"] for g in gs.values()}
    r["verdict"] = verdicts.pop() if len(verdicts) == 1 else "disagree"
    r["verdict_regex"] = next(iter(gs.values())).get("verdict_regex")
    r["verdict_ok"] = int(r["verdict"] == case["expected"])
    hits = [all(g.get("planted", {}).get(k) is True for g in gs.values()) for k in planted]
    anyhit = [any(g.get("planted", {}).get(k) is True for g in gs.values()) for k in planted]
    r["planted_total"], r["planted_found"] = len(planted), sum(hits)
    r["planted_disagree"] = sum(a != b for a, b in zip(hits, anyhit))
    r["false_blockers"] = max(int(g.get("false_blockers") or 0) for g in gs.values())
    r["forbidden_raised"] = int(any(g.get("forbidden_raised") for g in gs.values()))
    head = "\n".join(report.strip().splitlines()[:5])
    # Checagem determinística do P2 de except-zera: o cabeçalho declara risco alto.
    r["risk_high_in_header"] = int(bool(re.search(r"(risco|risk)\W{0,6}\**\s*(alto|high)|high risk", head, re.I)))
    mm = re.search(r"(?:modelo|model)\W{0,4}\**\s*([^.·\n]{3,40})", head, re.I)
    r["self_reported_model"] = mm.group(1).strip(" *`") if mm else ""
    return r


def rows_a(w, cases):
    rows = []
    for m in sorted((w / "expA/results").rglob("meta.json")):
        meta = json.loads(m.read_text(encoding="utf-8"))
        gs = load_grade(m.parent)
        if meta.get("exit") == 0 and not gs:
            continue  # ainda sem grader: não dá para julgar, e não é falha do braço
        rep = (m.parent / "report.md").read_text(encoding="utf-8", errors="replace") if (m.parent / "report.md").exists() else ""
        rows.append(row_a(meta, gs, cases[meta["case"]], rep))
    return rows


def summary_a(rows, cases):
    by = defaultdict(list)
    for r in rows:
        by[(r["arm"], r["case_set"])].append(r)
    out = []
    for (arm, cset), rs in sorted(by.items()):
        ok = [r for r in rs if not r["failed"]]
        clean = [r for r in rs if not cases[r["case"]]["planted"]]
        pt = sum(r["planted_total"] for r in rs)
        correct = sum(r["verdict_ok"] for r in rs)
        out.append({
            "arm": arm, "case_set": cset, "runs": len(rs), "failed_runs": len(rs) - len(ok),
            "cases": len({r["case"] for r in rs}),
            "verdict_accuracy": round(correct / len(rs), 3),
            "planted_recall": round(sum(r["planted_found"] for r in rs) / pt, 3) if pt else None,
            "false_blockers_per_run": round(st.mean(r["false_blockers"] for r in ok), 2) if ok else None,
            "clean_cases_false_alarm": round(st.mean(int(r["verdict"] != "ready" or r["forbidden_raised"]) for r in clean), 3) if clean else None,
            "median_seconds": round(st.median(r["seconds"] for r in rs)),
            "median_cost_low_usd": round(st.median(r["cost_low_usd"] for r in rs), 3),
            "median_cost_high_usd": round(st.median(r["cost_high_usd"] for r in rs), 3),
            "median_cost_reported_usd": round(st.median(r["cost_reported_usd"] for r in rs), 3) if all(r["cost_reported_usd"] for r in rs) else None,
            "cost_low_per_correct_verdict_usd": per_success(sum(r["cost_low_usd"] for r in rs), correct),
            "median_output_tokens": round(st.median(r["output_tokens"] for r in rs)),
            "repo_dirty": sum(bool(r["repo_dirty"]) for r in rs),
            "except_zera_risk_high": f"{sum(r['risk_high_in_header'] for r in rs if r['case'] == 'except-zera')}/{sum(r['case'] == 'except-zera' for r in rs)}",
            "grader_disagreements": sum(r["verdict"] == "disagree" for r in rs) + sum(r["planted_disagree"] for r in rs),
        })
    return out


# ---------- Experimento B ----------
def rows_b(sets):
    brows = []
    for agent, root in sets.items():
        for m in sorted(root.rglob("meta.json")):
            meta = json.loads(m.read_text(encoding="utf-8"))
            g = m.parent / "grade.json"
            crit = json.loads(g.read_text(encoding="utf-8")) if g.exists() else {}
            if meta.get("exit") == 0 and not crit:
                continue  # ainda sem correção
            brows.append({"agent": agent, "case": meta["case"], "arm": meta["arm"], "attempt": meta["attempt"],
                          "exit": meta.get("exit"), "failed": int(meta.get("exit") != 0),
                          "passed": sum(crit.values()), "total": len(crit) or 1,
                          "all_passed": int(bool(crit) and all(crit.values()) and meta.get("exit") == 0),
                          "seconds": meta.get("seconds"), "cost_usd": meta.get("cost_usd"),
                          "failed_criteria": ";".join(k for k, v in crit.items() if not v)})
    return brows


def summary_b(brows):
    by = defaultdict(list)
    for r in brows:
        by[(r["agent"], r["case"], r["arm"])].append(r)
    out = []
    for (agent, case, arm), rs in sorted(by.items()):
        costs = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
        full = sum(r["all_passed"] for r in rs)
        secs = [r["seconds"] for r in rs if r["seconds"] is not None]
        out.append({"agent": agent, "case": case, "arm": arm, "runs": len(rs), "failed_runs": sum(r["failed"] for r in rs),
                    "all_passed_runs": full, "mean_criteria": round(st.mean(r["passed"] / r["total"] for r in rs), 3),
                    "mean_cost_usd": round(st.mean(costs), 4) if costs else None,
                    "cost_per_all_passed_usd": per_success(sum(costs), full) if len(costs) == len(rs) else None,
                    "median_seconds": round(st.median(secs)) if secs else None})
    return out


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["empty"])
        w.writeheader(); w.writerows(rows)


def main():
    w = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve()
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "charts").mkdir(parents=True, exist_ok=True)
    cases = load_cases(w)
    rows = rows_a(w, cases)
    summary = summary_a(rows, cases)
    write_csv(out / "data/expA_runs.csv", rows)
    write_csv(out / "data/expA_summary.csv", summary)
    b_sets = {"Claude Opus 5.5 (Claude Code)": w / "expB/results", "Gemini 4 Neon (Antigravity)": w / "expB/results-agy-ptbr"}
    brows = rows_b(b_sets)
    write_csv(out / "data/expB_runs.csv", brows)
    write_csv(out / "data/expB_summary.csv", summary_b(brows))
    # Os gráficos mostram só o lote de desenvolvimento; o reservado fica nas tabelas, separado.
    charts(out, [s for s in summary if s["case_set"] == "dev"], brows)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(len(rows), "runs A;", len(brows), "runs B")


# ---------- Gráficos ----------
def charts(OUT, summary, brows):
    import matplotlib
    matplotlib.use("svg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

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


    S = {s["arm"]: s for s in summary}
    ARM_ORDER = [a for a in ("astra-max", "neon-xhigh", "opus-max", "upstream-astra-max", "upstream-neon-xhigh",
                             "upstream-opus-max") if a in S]

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


if __name__ == "__main__":
    main()
