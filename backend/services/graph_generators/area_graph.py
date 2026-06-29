"""services/graph_generators/area_graph.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config   = config or {}
    title    = config.get("title", "Area Graph")
    x_col    = config.get("x_col")
    y_cols   = config.get("y_cols") or []
    stacked  = config.get("stacked", False)

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

    x = df[x_col].astype(str)
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    if stacked and len(y_cols) > 1:
        data = {c: pd.to_numeric(df[c], errors="coerce").fillna(0).values for c in y_cols}
        ax.stackplot(range(len(x)), data.values(),
                     labels=list(data.keys()),
                     colors=PALETTE[:len(y_cols)], alpha=0.8)
        ax.set_xticks(range(len(x)))
        ax.set_xticklabels(x, rotation=35, ha="right", fontsize=9)
    else:
        for i, col in enumerate(y_cols):
            y = pd.to_numeric(df[col], errors="coerce").fillna(0)
            ax.fill_between(range(len(x)), y, alpha=0.35, color=PALETTE[i % len(PALETTE)])
            ax.plot(range(len(x)), y, color=PALETTE[i % len(PALETTE)],
                    lw=2, label=col, marker="o", markersize=4)
        ax.set_xticks(range(len(x)))
        ax.set_xticklabels(x, rotation=35, ha="right", fontsize=9)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(x_col)
    ax.set_ylabel("Value")
    if len(y_cols) > 1:
        ax.legend(loc="upper left")
    plt.tight_layout()
    url = save_fig(fig, "area")
    return ok_result(url, f"Area graph of {', '.join(y_cols)} over {x_col}.")
