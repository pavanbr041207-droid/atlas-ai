"""services/graph_generators/box_plot.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config   = config or {}
    title    = config.get("title", "Box Plot")
    cols     = config.get("cols") or []
    group_col = config.get("group_col")
    notch    = config.get("notch", False)

    if df is None or df.empty:
        return error_result("No data provided.")

    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not cols:
        cols = num_cols
    if not cols:
        return error_result("Need at least one numeric column.")

    apply_style()

    if group_col and group_col in df.columns:
        # One box per group per column
        groups   = df[group_col].unique()
        fig, axes = plt.subplots(1, len(cols), figsize=(max(FIG_W, 4 * len(cols)), FIG_H))
        if len(cols) == 1:
            axes = [axes]
        for ax, col in zip(axes, cols):
            data_by_group = [pd.to_numeric(df[df[group_col] == g][col], errors="coerce").dropna()
                             for g in groups]
            bp = ax.boxplot(data_by_group, notch=notch, patch_artist=True,
                            medianprops={"color": "black", "lw": 2})
            for patch, color in zip(bp["boxes"], PALETTE):
                patch.set_facecolor(color)
                patch.set_alpha(0.75)
            ax.set_xticklabels([str(g) for g in groups], rotation=30, ha="right")
            ax.set_title(col, fontsize=11, fontweight="bold")
    else:
        data = [pd.to_numeric(df[c], errors="coerce").dropna().values for c in cols]
        fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
        bp = ax.boxplot(data, notch=notch, patch_artist=True,
                        medianprops={"color": "black", "lw": 2})
        for patch, color in zip(bp["boxes"], PALETTE):
            patch.set_facecolor(color)
            patch.set_alpha(0.75)
        ax.set_xticklabels(cols, rotation=30, ha="right", fontsize=9)
        ax.set_ylabel("Value")

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    url = save_fig(fig, "boxplot")
    return ok_result(url, f"Box plot of {', '.join(cols)}.")
