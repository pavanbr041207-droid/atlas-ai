"""services/graph_generators/scatter_plot.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Scatter Plot")
    x_col     = config.get("x_col")
    y_col     = config.get("y_col")
    color_col = config.get("color_col")   # optional grouping column
    trendline = config.get("trendline", True)

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    if len(num_cols) < 2:
        return error_result("Need at least 2 numeric columns for a scatter plot.")

    if not x_col:
        x_col = num_cols[0]
    if not y_col:
        y_col = num_cols[1] if len(num_cols) > 1 else num_cols[0]

    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    mask = x.notna() & y.notna()
    x, y = x[mask], y[mask]

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    if color_col and color_col in df.columns:
        groups = df[color_col][mask].unique()
        for i, grp in enumerate(groups):
            sel = df[color_col][mask] == grp
            ax.scatter(x[sel], y[sel], label=str(grp), color=PALETTE[i % len(PALETTE)],
                       alpha=0.75, s=60, edgecolors="white", linewidth=0.5)
        ax.legend()
    else:
        ax.scatter(x, y, color=PALETTE[0], alpha=0.75, s=60,
                   edgecolors="white", linewidth=0.5)

    if trendline and len(x) > 1:
        try:
            z   = np.polyfit(x, y, 1)
            p   = np.poly1d(z)
            xs  = np.linspace(x.min(), x.max(), 200)
            ax.plot(xs, p(xs), color=PALETTE[3], linestyle="--", lw=1.5, label="Trend")
            ax.legend()
        except Exception:
            pass

    corr = x.corr(y)
    ax.set_title(f"{title}  (r = {corr:.2f})", fontsize=14, fontweight="bold")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    plt.tight_layout()
    url = save_fig(fig, "scatter")
    return ok_result(url, f"Scatter plot of {y_col} vs {x_col}. Correlation: {corr:.2f}.")
