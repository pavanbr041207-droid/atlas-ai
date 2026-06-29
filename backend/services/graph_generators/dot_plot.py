"""services/graph_generators/dot_plot.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Dot Plot")
    label_col = config.get("label_col")
    value_cols = config.get("value_cols") or []

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not label_col:
        label_col = cat_cols[0] if cat_cols else df.columns[0]
    if not value_cols:
        value_cols = num_cols if num_cols else [c for c in df.columns if c != label_col]
    if not value_cols:
        return error_result("Need at least one numeric column.")

    labels = df[label_col].astype(str).tolist()
    apply_style()

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    for i, col in enumerate(value_cols):
        vals = pd.to_numeric(df[col], errors="coerce").tolist()
        y    = range(len(labels))
        ax.scatter(vals, y, color=PALETTE[i % len(PALETTE)], s=80,
                   zorder=3, label=col)
        # connecting lines
        for yi, v in zip(y, vals):
            ax.hlines(yi, 0, v, color=PALETTE[i % len(PALETTE)],
                      lw=1.2, alpha=0.4, zorder=2)

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Value")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.axvline(0, color="black", lw=0.7)
    if len(value_cols) > 1:
        ax.legend(fontsize=9)
    plt.tight_layout()
    url = save_fig(fig, "dotplot")
    return ok_result(url, f"Dot plot of {', '.join(value_cols)} by {label_col}.")
