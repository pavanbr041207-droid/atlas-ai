"""services/graph_generators/bar_graph.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config   = config or {}
    title    = config.get("title", "Bar Graph")
    x_col    = config.get("x_col")
    y_cols   = config.get("y_cols") or []
    orient   = config.get("orient", "vertical")   # vertical | horizontal

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not x_col:
        x_col = cat_cols[0] if cat_cols else df.columns[0]
    if not y_cols:
        y_cols = num_cols if num_cols else [c for c in df.columns if c != x_col]
    if not y_cols:
        return error_result("Need at least one numeric column for the Y-axis.")

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    n    = len(y_cols)
    x    = range(len(df))
    w    = 0.8 / n

    for i, col in enumerate(y_cols):
        positions = [xi + i * w - (n - 1) * w / 2 for xi in x]
        vals      = pd.to_numeric(df[col], errors="coerce").fillna(0)
        color     = PALETTE[i % len(PALETTE)]
        if orient == "horizontal":
            ax.barh(positions, vals, height=w, label=col, color=color)
        else:
            ax.bar(positions, vals, width=w, label=col, color=color)

    if orient == "horizontal":
        ax.set_yticks(list(x))
        ax.set_yticklabels(df[x_col].astype(str), fontsize=9)
        ax.set_xlabel("Value")
        ax.set_ylabel(x_col)
    else:
        ax.set_xticks(list(x))
        ax.set_xticklabels(df[x_col].astype(str), rotation=35, ha="right", fontsize=9)
        ax.set_ylabel("Value")
        ax.set_xlabel(x_col)

    ax.set_title(title, fontsize=14, fontweight="bold")
    if n > 1:
        ax.legend()

    # Value labels
    for patch in ax.patches:
        val = patch.get_height() if orient == "vertical" else patch.get_width()
        if val != 0:
            if orient == "vertical":
                ax.annotate(f"{val:.1f}", (patch.get_x() + patch.get_width()/2, val),
                            ha="center", va="bottom", fontsize=8)
            else:
                ax.annotate(f"{val:.1f}", (val, patch.get_y() + patch.get_height()/2),
                            ha="left", va="center", fontsize=8)

    plt.tight_layout()
    url = save_fig(fig, "bar")
    return ok_result(url, f"Bar graph of {', '.join(y_cols)} by {x_col}.")
