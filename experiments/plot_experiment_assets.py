#!/usr/bin/env python3
"""Generate report/PPT figures for the SOC alert triage experiment."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-security-project")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = ROOT / "experiments" / "assets"
RESULT_CANDIDATES = [
    ROOT / "outputs" / "hybrid_alertbert_qwen",
    ROOT / "outputs" / "smoke_qwen_256",
    ROOT / "outputs" / "smoke_scipy",
]


COLORS = {
    "blue": "#2f6fbb",
    "green": "#2f9e76",
    "orange": "#e58a2a",
    "red": "#cc4c4c",
    "gray": "#6b7280",
    "light": "#edf2f7",
    "dark": "#1f2937",
}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def resolve_results_dir(path: str | None) -> Path:
    if path:
        return Path(path).resolve()
    for candidate in RESULT_CANDIDATES:
        if (candidate / "clusters.csv").exists():
            return candidate
    raise FileNotFoundError("No result directory found. Run hybrid_alertbert_qwen.py first or pass --results-dir.")


def save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def set_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#cbd5e1",
            "axes.labelcolor": COLORS["dark"],
            "xtick.color": COLORS["dark"],
            "ytick.color": COLORS["dark"],
            "font.size": 10,
            "axes.titleweight": "bold",
            "axes.titlesize": 13,
        }
    )


def fig_pipeline(asset_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(13.5, 3.2))
    ax.axis("off")
    boxes = [
        ("AIT-ADS-A\nmixed alerts", 0.04, COLORS["blue"]),
        ("TimeDelta\nbaseline", 0.22, COLORS["gray"]),
        ("AlertBERT\nsemantic clusters", 0.40, COLORS["green"]),
        ("Uncertainty\nscoring", 0.58, COLORS["orange"]),
        ("Qwen3-8B\non-demand triage", 0.76, COLORS["red"]),
        ("Analyst queue\nattack / uncertain", 0.91, COLORS["dark"]),
    ]
    for text, x, color in boxes:
        ax.text(
            x,
            0.55,
            text,
            ha="center",
            va="center",
            color="white",
            fontsize=11,
            fontweight="bold",
            bbox={"boxstyle": "round,pad=0.55,rounding_size=0.08", "fc": color, "ec": color},
            transform=ax.transAxes,
        )
    for i in range(len(boxes) - 1):
        x0 = boxes[i][1] + 0.065
        x1 = boxes[i + 1][1] - 0.065
        ax.annotate("", xy=(x1, 0.55), xytext=(x0, 0.55), arrowprops={"arrowstyle": "->", "lw": 2, "color": COLORS["dark"]}, xycoords=ax.transAxes)
    ax.text(0.5, 0.15, "Small model handles scale; LLM handles only low-confidence clusters.", ha="center", color=COLORS["gray"], transform=ax.transAxes)
    path = asset_dir / "fig1_pipeline.png"
    save(fig, path)
    return path


def fig_attack_labels(asset_dir: Path) -> Path:
    labels_path = ROOT / "data" / "ait_ads" / "labels.csv"
    labels = pd.read_csv(labels_path)
    labels["duration_min"] = (labels["end"] - labels["start"]) / 60.0
    pivot = labels.pivot_table(index="scenario", columns="attack", values="duration_min", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(sorted(pivot.index), axis=0)
    fig, ax = plt.subplots(figsize=(12, 5.8))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlGnBu")
    ax.set_title("AIT-ADS attack-phase coverage by scenario")
    ax.set_xlabel("Attack phase")
    ax.set_ylabel("Scenario")
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=35, ha="right")
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Duration (minutes)")
    path = asset_dir / "fig2_attack_phase_matrix.png"
    save(fig, path)
    return path


def fig_cluster_overview(clusters: pd.DataFrame, asset_dir: Path) -> Path:
    total = len(clusters)
    attack = int(clusters.get("is_attack", pd.Series(dtype=bool)).sum()) if "is_attack" in clusters else 0
    benign = total - attack
    cluster_sizes = clusters.groupby("cluster").size().sort_values(ascending=False)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.5), gridspec_kw={"width_ratios": [1, 1.4]})
    ax1.bar(["Benign/noise", "Attack"], [benign, attack], color=[COLORS["blue"], COLORS["red"]])
    ax1.set_title("Alert composition in selected result set")
    ax1.set_ylabel("Alerts")
    for i, v in enumerate([benign, attack]):
        ax1.text(i, v + max(total * 0.02, 1), f"{v:,}", ha="center", va="bottom")
    top = cluster_sizes.head(20).sort_values()
    ax2.barh([str(i) for i in top.index], top.values, color=COLORS["green"])
    ax2.set_title("Top 20 AlertBERT cluster sizes")
    ax2.set_xlabel("Alerts per cluster")
    ax2.set_ylabel("Cluster ID")
    path = asset_dir / "fig3_cluster_overview.png"
    save(fig, path)
    return path


def fig_uncertainty(uncertainty: pd.DataFrame, asset_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.8))
    vals = uncertainty["uncertainty"].dropna()
    ax.hist(vals, bins=min(30, max(8, len(vals) // 4)), color=COLORS["orange"], edgecolor="white")
    threshold = uncertainty.sort_values("uncertainty", ascending=False).head(max(1, math.ceil(len(uncertainty) * 0.05)))["uncertainty"].min()
    ax.axvline(threshold, color=COLORS["red"], linestyle="--", linewidth=2, label="Top 5% handoff threshold")
    ax.set_title("Cluster uncertainty distribution")
    ax.set_xlabel("Uncertainty score")
    ax.set_ylabel("Clusters")
    ax.legend()
    path = asset_dir / "fig4_uncertainty_distribution.png"
    save(fig, path)
    return path


def fig_size_vs_uncertainty(uncertainty: pd.DataFrame, asset_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.2))
    sizes = uncertainty["cluster_size"].clip(lower=1)
    colors = uncertainty.get("true_attack_ratio", pd.Series(np.zeros(len(uncertainty))))
    sc = ax.scatter(sizes, uncertainty["uncertainty"], c=colors, cmap="Reds", s=45, alpha=0.78, edgecolors="#334155", linewidths=0.25)
    ax.set_xscale("log")
    ax.set_title("Cluster size vs. uncertainty")
    ax.set_xlabel("Cluster size (log scale)")
    ax.set_ylabel("Uncertainty score")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("True attack ratio")
    path = asset_dir / "fig5_cluster_size_vs_uncertainty.png"
    save(fig, path)
    return path


def finite_metric(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, dict):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def fig_metrics(results_dir: Path, asset_dir: Path) -> Path:
    td = load_json(results_dir / "timedelta_test_metrics.json", {})
    ab = load_json(results_dir / "alertbert_test_metrics.json", {})
    hybrid = load_json(results_dir / "hybrid_metrics.json", {})
    td_noise = td.get("noise", {}) if isinstance(td, dict) else {}
    ab_noise = ab.get("alertbert_macro_noise", {}) if isinstance(ab, dict) else {}
    rows = [
        ("TimeDelta", finite_metric(td_noise, "f1")),
        ("AlertBERT", finite_metric(ab_noise, "f1")),
        ("Hybrid triage", finite_metric(hybrid, "attack_f1")),
    ]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    values = [0 if v is None else v for _, v in rows]
    bars = ax.bar([r[0] for r in rows], values, color=[COLORS["gray"], COLORS["green"], COLORS["orange"]])
    ax.set_ylim(0, 1.0)
    ax.set_title("F1 comparison (available result set)")
    ax.set_ylabel("F1")
    for bar, (_, value) in zip(bars, rows):
        label = "n/a" if value is None else f"{value:.3f}"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03, label, ha="center")
    path = asset_dir / "fig6_metric_comparison.png"
    save(fig, path)
    return path


def fig_llm_cost(results_dir: Path, asset_dir: Path) -> Path:
    hybrid = load_json(results_dir / "hybrid_metrics.json", {})
    actual = float(hybrid.get("input_tokens", 0) + hybrid.get("output_tokens", 0))
    pure = float(hybrid.get("pure_llm_cluster_token_estimate", 0))
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    values = [max(actual, 1), max(pure, 1)]
    ax.bar(["On-demand LLM", "Pure cluster-level LLM"], values, color=[COLORS["green"], COLORS["red"]])
    ax.set_yscale("log")
    ax.set_title("Token cost comparison")
    ax.set_ylabel("Tokens (log scale)")
    labels = [f"{actual:,.0f}", f"{pure:,.0f}"]
    for i, label in enumerate(labels):
        ax.text(i, values[i] * 1.15, label, ha="center")
    ratio = (actual / pure) if pure else 0
    ax.text(0.5, 0.08, f"On-demand ratio: {ratio:.2%}" if pure else "Pure LLM estimate unavailable", transform=ax.transAxes, ha="center", color=COLORS["gray"])
    path = asset_dir / "fig7_token_cost.png"
    save(fig, path)
    return path


def fig_qwen_decisions(results_dir: Path, asset_dir: Path) -> Path:
    decisions = pd.DataFrame(load_jsonl(results_dir / "qwen_decisions.jsonl"))
    hybrid = load_json(results_dir / "hybrid_metrics.json", {})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    if decisions.empty:
        ax1.text(0.5, 0.5, "No LLM decisions", ha="center", va="center")
        ax1.axis("off")
    else:
        counts = decisions["decision"].value_counts()
        ax1.bar(counts.index, counts.values, color=COLORS["blue"])
        ax1.set_title("Qwen decisions")
        ax1.set_ylabel("Clusters")
        for i, v in enumerate(counts.values):
            ax1.text(i, v + 0.03, str(v), ha="center")
    retained = float(hybrid.get("false_positive_alerts_retained", 0))
    benign = float(hybrid.get("auto_benign_alerts", 0))
    ax2.bar(["Retained FP/noise", "Auto-benign"], [retained, benign], color=[COLORS["orange"], COLORS["green"]])
    ax2.set_title("Noise-handling effect")
    ax2.set_ylabel("Alerts")
    for i, v in enumerate([retained, benign]):
        ax2.text(i, v + max((retained + benign) * 0.02, 1), f"{v:,.0f}", ha="center")
    path = asset_dir / "fig8_qwen_triage.png"
    save(fig, path)
    return path


def write_manifest(paths: list[Path], results_dir: Path, asset_dir: Path) -> None:
    captions = {
        "fig1_pipeline.png": "Hybrid pipeline: AlertBERT handles scale, Qwen handles low-confidence clusters.",
        "fig2_attack_phase_matrix.png": "AIT-ADS contains multi-scenario, multi-phase attack labels.",
        "fig3_cluster_overview.png": "Alert/noise composition and largest AlertBERT clusters in the selected result set.",
        "fig4_uncertainty_distribution.png": "Only the highest-uncertainty clusters are handed off to Qwen.",
        "fig5_cluster_size_vs_uncertainty.png": "Cluster size and uncertainty relationship.",
        "fig6_metric_comparison.png": "F1 comparison for available baseline/hybrid outputs.",
        "fig7_token_cost.png": "Token-cost contrast between on-demand and pure LLM usage.",
        "fig8_qwen_triage.png": "Qwen decision counts and auto-benign effect.",
    }
    lines = [f"# Experiment Assets\n", f"- Results directory: `{results_dir}`\n"]
    for path in paths:
        lines.append(f"- `{path.name}`: {captions.get(path.name, '')}\n")
    (asset_dir / "manifest.md").write_text("".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default=None, help="Directory containing clusters.csv and metrics JSON files.")
    parser.add_argument("--asset-dir", default=str(DEFAULT_ASSET_DIR), help="Where PNG figures should be written.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    set_style()
    results_dir = resolve_results_dir(args.results_dir)
    asset_dir = Path(args.asset_dir).resolve()
    clusters = pd.read_csv(results_dir / "clusters.csv")
    uncertainty = pd.read_csv(results_dir / "cluster_uncertainty.csv")
    paths = [
        fig_pipeline(asset_dir),
        fig_attack_labels(asset_dir),
        fig_cluster_overview(clusters, asset_dir),
        fig_uncertainty(uncertainty, asset_dir),
        fig_size_vs_uncertainty(uncertainty, asset_dir),
        fig_metrics(results_dir, asset_dir),
        fig_llm_cost(results_dir, asset_dir),
        fig_qwen_decisions(results_dir, asset_dir),
    ]
    write_manifest(paths, results_dir, asset_dir)
    print(f"Wrote {len(paths)} figures to {asset_dir}")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
