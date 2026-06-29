"""services/graph_generators/bubble_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Bubble Chart")
    x_col     = config.get("x_col")
    y_col     = config.get("y_col")
    size_col  = config.get("size_col")
    label_col = config.get("label_col")

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if len(num_cols) < 2:
        return error_result("Need at least 2 numeric columns (x, y). 3rd numeric used for bubble size.")

    if not x_col:     x_col     = num_cols[0]
    if not y_col:     y_col     = num_cols[1] if len(num_cols) > 1 else num_cols[0]
    if not size_col:  size_col  = num_cols[2] if len(num_cols) > 2 else None
    if not label_col: label_col = cat_cols[0] if cat_cols else None

    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")

    if size_col:
        raw_s = pd.to_numeric(df[size_col], errors="coerce").fillna(0)
        s_min, s_max = raw_s.min(), raw_s.max()
        sizes = ((raw_s - s_min) / (s_max - s_min + 1e-9) * 1500 + 50).values
    else:
        sizes = 200

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    scatter = ax.scatter(x, y, s=sizes,
                          c=range(len(df)), cmap="tab10", alpha=0.75,
                          edgecolors="white", linewidth=0.8)

    if label_col:
        for _, row in df.iterrows():
            ax.annotate(str(row[label_col]),
                        (pd.to_numeric(row[x_col], errors="coerce"),
                         pd.to_numeric(row[y_col], errors="coerce")),
                        ha="center", va="bottom", fontsize=8)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    if size_col:
        ax.annotate(f"Bubble size = {size_col}", xy=(0.02, 0.97),
                    xycoords="axes fraction", fontsize=9, va="top")
    plt.tight_layout()
    url = save_fig(fig, "bubble")
    return ok_result(url, f"Bubble chart: x={x_col}, y={y_col}" +
                     (f", size={size_col}" if size_col else "") + ".")
