"""services/graph_generators/histogram.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config   = config or {}
    title    = config.get("title", "Histogram")
    col      = config.get("col")
    bins     = config.get("bins", "auto")
    kde      = config.get("kde", True)

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not col:
        col = num_cols[0] if num_cols else None
    if not col:
        return error_result("Need a numeric column for the histogram.")

    data = pd.to_numeric(df[col], errors="coerce").dropna()
    if data.empty:
        return error_result(f"Column '{col}' has no numeric values.")

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    n, edges, patches = ax.hist(data, bins=bins, color=PALETTE[0],
                                 edgecolor="white", alpha=0.85)

    if kde:
        from scipy.stats import gaussian_kde
        try:
            kde_func = gaussian_kde(data)
            x_range  = np.linspace(data.min(), data.max(), 300)
            ax2      = ax.twinx()
            ax2.plot(x_range, kde_func(x_range), color=PALETTE[1], lw=2, label="KDE")
            ax2.set_ylabel("Density")
            ax2.legend(loc="upper right")
        except Exception:
            pass

    ax.set_title(title or f"Histogram of {col}", fontsize=14, fontweight="bold")
    ax.set_xlabel(col)
    ax.set_ylabel("Frequency")
    ax.axvline(data.mean(), color=PALETTE[3], linestyle="--", lw=1.5, label=f"Mean: {data.mean():.2f}")
    ax.legend()
    plt.tight_layout()
    url = save_fig(fig, "histogram")
    return ok_result(url, f"Histogram of '{col}' with {len(data)} values. Mean: {data.mean():.2f}.")
