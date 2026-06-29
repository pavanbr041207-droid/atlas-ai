"""services/graph_generators/heatmap.py — data-based heatmap (not geo)"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config   = config or {}
    title    = config.get("title", "Heat Map")
    index_col = config.get("index_col")
    cmap     = config.get("cmap", "YlOrRd")
    annot    = config.get("annot", True)

    if df is None or df.empty:
        return error_result("No data provided.")

    cat_cols = df.select_dtypes(exclude="number").columns.tolist()
    num_cols = df.select_dtypes(include="number").columns.tolist()

    if not num_cols:
        return error_result("Heatmap needs numeric columns.")

    if index_col and index_col in df.columns:
        matrix = df.set_index(index_col)[num_cols]
    elif cat_cols:
        matrix = df.set_index(cat_cols[0])[num_cols]
    else:
        matrix = df[num_cols]

    # Correlation heatmap if single column group
    if len(num_cols) >= 2 and config.get("correlation", False):
        matrix = df[num_cols].corr()

    h = max(5, len(matrix) * 0.5)
    w = max(FIG_W, len(matrix.columns) * 0.9)
    fig, ax = plt.subplots(figsize=(w, h))

    data = matrix.values.astype(float)
    im   = ax.imshow(data, cmap=cmap, aspect="auto")
    plt.colorbar(im, ax=ax, shrink=0.8)

    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index, fontsize=9)

    if annot:
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                val = data[i, j]
                if not np.isnan(val):
                    text_color = "white" if abs(val) > (np.nanmax(data) * 0.6) else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                            fontsize=8, color=text_color)

    ax.set_title(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    url = save_fig(fig, "heatmap")
    return ok_result(url, f"Heatmap of {len(num_cols)} variables × {len(matrix)} rows.")
