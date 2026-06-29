"""services/graph_generators/pareto_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Pareto Chart")
    label_col = config.get("label_col")
    value_col = config.get("value_col")

    if df is None or df.empty:
        return error_result("No data provided.")

    cat_cols = df.select_dtypes(exclude="number").columns.tolist()
    num_cols = df.select_dtypes(include="number").columns.tolist()

    if not label_col:
        label_col = cat_cols[0] if cat_cols else df.columns[0]
    if not value_col:
        value_col = num_cols[0] if num_cols else (df.columns[1] if len(df.columns) > 1 else None)
    if not value_col:
        return error_result("Need a numeric value column.")

    # Sort descending
    df2 = df[[label_col, value_col]].copy()
    df2[value_col] = pd.to_numeric(df2[value_col], errors="coerce").fillna(0)
    df2 = df2.sort_values(value_col, ascending=False).reset_index(drop=True)

    cumsum  = df2[value_col].cumsum()
    cumperc = cumsum / df2[value_col].sum() * 100

    apply_style()
    fig, ax1 = plt.subplots(figsize=(FIG_W, FIG_H))
    ax2 = ax1.twinx()

    x = np.arange(len(df2))
    bars = ax1.bar(x, df2[value_col], color=PALETTE[0], alpha=0.85,
                   edgecolor="white", linewidth=0.8, label=value_col)
    ax2.plot(x, cumperc, color=PALETTE[3], marker="D", ms=5, lw=2, label="Cumulative %")
    ax2.axhline(80, color="red", linestyle="--", lw=1, label="80% line")
    ax2.set_ylim(0, 110)
    ax2.set_ylabel("Cumulative %", color=PALETTE[3])
    ax2.yaxis.label.set_color(PALETTE[3])

    # Value labels on bars
    for bar, val in zip(bars, df2[value_col]):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + df2[value_col].max() * 0.01,
                 f"{val:.0f}", ha="center", va="bottom", fontsize=8)

    ax1.set_xticks(x)
    ax1.set_xticklabels(df2[label_col].astype(str), rotation=35, ha="right", fontsize=9)
    ax1.set_ylabel("Value")
    ax1.set_title(title, fontsize=14, fontweight="bold")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right", fontsize=9)
    plt.tight_layout()
    url = save_fig(fig, "pareto")
    return ok_result(url, f"Pareto chart of {value_col} by {label_col}.")
