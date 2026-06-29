"""services/graph_generators/waterfall_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, FIG_W, FIG_H


POS_COLOR   = "#4CAF50"
NEG_COLOR   = "#F44336"
TOTAL_COLOR = "#4C72B0"


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Waterfall Chart")
    label_col = config.get("label_col")
    value_col = config.get("value_col")
    total_labels = config.get("total_labels", [])   # which labels are totals

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

    labels = df[label_col].astype(str).tolist()
    values = pd.to_numeric(df[value_col], errors="coerce").fillna(0).tolist()

    # Compute running total and bottoms
    running = 0
    bottoms, heights, colors = [], [], []
    for i, (lbl, val) in enumerate(zip(labels, values)):
        is_total = lbl in total_labels or i == len(labels) - 1
        if is_total:
            bottoms.append(0)
            heights.append(running + val)
            colors.append(TOTAL_COLOR)
            running += val
        else:
            bottoms.append(running if val >= 0 else running + val)
            heights.append(abs(val))
            colors.append(POS_COLOR if val >= 0 else NEG_COLOR)
            running += val

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    x = np.arange(len(labels))

    ax.bar(x, heights, bottom=bottoms, color=colors, width=0.5,
           edgecolor="white", linewidth=0.8)

    # Connector lines
    for i in range(len(labels) - 1):
        top = bottoms[i] + heights[i]
        ax.plot([i + 0.25, i + 0.75], [top, top],
                color="grey", lw=0.8, linestyle="--")

    # Value labels
    for i, (b, h, v) in enumerate(zip(bottoms, heights, values)):
        ax.text(i, b + h + max(heights) * 0.01, f"{v:+.1f}",
                ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Value")
    ax.set_title(title, fontsize=14, fontweight="bold")

    legend_patches = [
        mpatches.Patch(color=POS_COLOR,   label="Positive"),
        mpatches.Patch(color=NEG_COLOR,   label="Negative"),
        mpatches.Patch(color=TOTAL_COLOR, label="Total"),
    ]
    ax.legend(handles=legend_patches, loc="upper left", fontsize=9)
    plt.tight_layout()
    url = save_fig(fig, "waterfall")
    return ok_result(url, f"Waterfall chart of {value_col} by {label_col}.")
