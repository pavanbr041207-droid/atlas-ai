"""services/graph_generators/radar_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Radar Chart")
    label_col = config.get("label_col")
    cols      = config.get("cols") or []

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not label_col:
        label_col = cat_cols[0] if cat_cols else None
    if not cols:
        cols = num_cols

    if len(cols) < 3:
        return error_result("Need at least 3 numeric columns for a radar chart.")

    # Normalise each column 0-1
    ndf = df[cols].copy()
    for c in cols:
        ndf[c] = pd.to_numeric(ndf[c], errors="coerce").fillna(0)
        mn, mx = ndf[c].min(), ndf[c].max()
        ndf[c] = (ndf[c] - mn) / (mx - mn + 1e-9)

    N = len(cols)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_H, FIG_H), subplot_kw={"polar": True})

    for i, row in ndf.iterrows():
        vals  = row.tolist() + [row.iloc[0]]
        label = str(df[label_col].iloc[i]) if label_col else str(i)
        color = PALETTE[i % len(PALETTE)]
        ax.plot(angles, vals, color=color, lw=2, label=label)
        ax.fill(angles, vals, color=color, alpha=0.15)

    ax.set_thetagrids(np.degrees(angles[:-1]), cols, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    if label_col and len(df) <= 8:
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=8)

    plt.tight_layout()
    url = save_fig(fig, "radar")
    return ok_result(url, f"Radar chart comparing {', '.join(cols)}.")
