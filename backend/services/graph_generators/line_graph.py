"""services/graph_generators/line_graph.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config = config or {}
    title  = config.get("title", "Line Graph")
    x_col  = config.get("x_col")
    y_cols = config.get("y_cols") or []
    markers = config.get("markers", True)

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not x_col:
        x_col = cat_cols[0] if cat_cols else df.columns[0]
    if not y_cols:
        y_cols = num_cols if num_cols else [c for c in df.columns if c != x_col]
    if not y_cols:
        return error_result("Need at least one numeric column.")

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    marker_styles = ["o", "s", "^", "D", "v", "P", "X", "*"]
    x_vals = df[x_col].astype(str)

    for i, col in enumerate(y_cols):
        y = pd.to_numeric(df[col], errors="coerce")
        mk = marker_styles[i % len(marker_styles)] if markers else None
        ax.plot(x_vals, y, marker=mk, label=col,
                color=PALETTE[i % len(PALETTE)], linewidth=2, markersize=6)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(x_col)
    ax.set_ylabel("Value")
    plt.xticks(rotation=35, ha="right", fontsize=9)
    if len(y_cols) > 1:
        ax.legend()
    plt.tight_layout()
    url = save_fig(fig, "line")
    return ok_result(url, f"Line graph of {', '.join(y_cols)} over {x_col}.")
