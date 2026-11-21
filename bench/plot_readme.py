"""Gera os gráficos do README a partir dos CSVs versionados."""

import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/data"
CHARTS = ROOT / "docs/charts"
INK = "#172b32"
MUTED = "#50636a"
GRID = "#dde6e8"
TEAL = "#00766f"
BASE = "#596f7d"
FAIL = "#a2441d"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial"],
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": MUTED,
    "axes.titlecolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "svg.fonttype": "none",
    "svg.hashsalt": "skills-readme",
})


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def format_pt(value):
    return f"{value:.1f}".replace(".", ",")


def style(axis, grid_axis):
    axis.spines[:].set_visible(False)
    axis.tick_params(length=0, pad=6)
    axis.set_axisbelow(True)
    axis.grid(axis=grid_axis, color=GRID, linewidth=0.8)


def plot_rubric():
    rounds = ("referencia", "estrutura", "exemplos", "transicoes", "decisoes", "entrega", "confirmacao")
    labels = ("Ref.", "Estrutura", "Exemplos", "Transições", "Decisões", "Entrega", "Confirmação")
    selected_rounds = {
        "spec": "exemplos",
        "implement": "referencia",
        "review": "estrutura",
        "close-spec": "entrega",
    }
    rows = read_csv("rubrica-nvidia.csv")
    scores = {(row["skill"], row["rodada"]): row for row in rows}
    figure, panels = plt.subplots(2, 2, figsize=(11, 6.3), sharey=True)
    figure.subplots_adjust(top=0.80, bottom=0.12, left=0.075, right=0.97, wspace=0.21, hspace=0.65)
    figure.text(0.075, 0.94, "Notas por rodada", fontsize=22, weight="bold")
    figure.text(0.075, 0.89, "NVIDIA SkillEvaluator · nota de 0 a 100", color=MUTED)

    for panel, (skill, selected_round) in zip(panels.flat, selected_rounds.items()):
        results = [scores[skill, run] for run in rounds]
        values = [float(row["nota"]) if row["nota"] else math.nan for row in results]
        selected = rounds.index(selected_round)
        best_approved = max(value for value, row in zip(values[:6], results[:6]) if row["status"] == "aprovada")
        if results[selected]["status"] != "aprovada" or values[selected] != best_approved:
            raise ValueError(f"A rodada selecionada para {skill} diverge dos dados.")
        style(panel, "y")
        panel.set_title(skill, loc="left", weight="bold", pad=8)
        panel.axvspan(5.5, 6.45, color="#e9f4f2", linewidth=0, zorder=0)
        panel.axhline(90, color=BASE, linewidth=0.8, linestyle=(0, (3, 3)))
        panel.plot(range(6), values[:6], color=BASE, linewidth=1.3, zorder=2)
        for index, row in enumerate(results):
            if not row["nota"]:
                panel.annotate("Sem nota", (index, 75), ha="center", fontsize=8, color=MUTED)
                continue
            if row["status"] == "aprovada":
                panel.scatter(index, values[index], color=TEAL, s=30, zorder=3)
            else:
                panel.scatter(index, values[index], marker="D", facecolor="white", edgecolor=FAIL, s=29, zorder=3)
        panel.scatter(selected, values[selected], facecolor="none", edgecolor=TEAL, s=104, linewidth=1.2, zorder=4)
        for index in (selected, 6):
            panel.annotate(
                format_pt(values[index]), (index, values[index]), xytext=(0, 8),
                textcoords="offset points", ha="center", fontsize=9, weight="bold", color=TEAL,
            )
        panel.set(xlim=(-0.35, 6.45), ylim=(70, 93), yticks=(70, 80, 90))
        panel.set_xticks(range(len(labels)), labels, rotation=27, ha="right", fontsize=9)

    figure.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", color=TEAL, label="Aprovada"),
            Line2D([], [], marker="D", linestyle="none", markerfacecolor="white", color=FAIL, label="Reprovada"),
            Line2D([], [], marker="o", linestyle="none", markerfacecolor="white", color=TEAL, label="Versão escolhida"),
        ],
        loc="upper right", bbox_to_anchor=(0.975, 0.95), ncol=3, frameon=False, fontsize=9,
    )
    return figure


def plot_reviewer():
    rows = {row["arm"]: row for row in read_csv("expA_summary.csv")}
    arms = ("astra-max", "upstream-astra-max", "neon-xhigh", "upstream-neon-xhigh")
    labels = (
        "GPT-6.2 Astra / daqui", "GPT-6.2 Astra / original",
        "Gemini 4 Neon / daqui", "Gemini 4 Neon / original",
    )
    figure, axis = plt.subplots(figsize=(10, 3.6))
    figure.subplots_adjust(left=0.27, right=0.89, top=0.73, bottom=0.20)
    figure.text(0.055, 0.91, "Problemas encontrados na revisão", fontsize=20, weight="bold")
    figure.text(0.055, 0.82, "Experimento A · porcentagem dos problemas incluídos nos casos de teste", color=MUTED)
    style(axis, "x")
    positions = (3.4, 2.65, 1.25, 0.5)
    for position, arm in zip(positions, arms):
        row = rows[arm]
        recall = float(row["planted_recall"])
        color = BASE if arm.startswith("upstream") else TEAL
        axis.barh(position, recall, height=0.36, color=color, zorder=2)
        axis.annotate(
            f"{format_pt(recall * 100)}% · n={row['runs']}", (recall, position),
            xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color=INK,
        )
    axis.set_yticks(positions, labels)
    axis.set(xlim=(0, 1.04), ylim=(0, 3.9), xticks=(0, 0.25, 0.5, 0.75, 1))
    axis.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    return figure


def plot_close():
    rows = {
        (row["case"], row["attempt"], row["arm"]): row
        for row in read_csv("expB_runs.csv")
        if row["agent"] == "Gemini 4 Neon (Antigravity)" and row["case"].startswith("close-")
    }
    figure, panels = plt.subplots(1, 2, figsize=(10, 3.8))
    figure.subplots_adjust(left=0.12, right=0.96, top=0.69, bottom=0.22, wspace=0.42)
    figure.text(0.075, 0.92, "Fechamento de spec", fontsize=20, weight="bold")
    figure.text(0.075, 0.84, "Experimento B · critérios cumpridos pelo Gemini 4 Neon via Antigravity", color=MUTED)
    for panel, (case, title) in zip(
        panels, (("close-feliz", "Squash local"), ("close-divergente", "SHAs divergentes")),
    ):
        style(panel, "x")
        panel.set_title(title, loc="left", weight="bold")
        total = int(rows[case, "1", "with"]["total"])
        for position, attempt in ((1.25, "1"), (0.35, "2")):
            for arm, label, color, offset in (
                ("without", "Sem skill", BASE, 0.13), ("with", "Com skill", TEAL, -0.13),
            ):
                result = rows[case, attempt, arm]
                passed = int(result["passed"])
                panel.barh(position + offset, passed, height=0.20, color=color, label=label, zorder=2)
                panel.annotate(
                    f"{passed}/{total}", (passed, position + offset), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=9,
                )
        panel.set_yticks((1.25, 0.35), ("Tentativa 1", "Tentativa 2"))
        panel.set(xlim=(0, total * 1.18), ylim=(0, 1.6), xticks=range(0, total + 1, total // 4))
    handles, labels = panels[0].get_legend_handles_labels()
    figure.legend(handles[:2], labels[:2], loc="lower center", ncol=2, frameon=False, fontsize=10)
    return figure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path, help="Também salva PNGs para conferência local.")
    args = parser.parse_args()
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
    for name, plot in (
        ("evolucao-rubrica", plot_rubric), ("revisores", plot_reviewer), ("fechamento", plot_close),
    ):
        figure = plot()
        svg = CHARTS / f"{name}.svg"
        figure.savefig(svg, metadata={"Date": None, "Title": figure.texts[0].get_text()})
        rendered = svg.read_text(encoding="utf-8")
        svg.write_text("\n".join(line.rstrip() for line in rendered.splitlines()) + "\n", encoding="utf-8")
        if args.preview_dir:
            figure.savefig(args.preview_dir / f"{name}.png", dpi=140)
        plt.close(figure)


if __name__ == "__main__":
    main()
