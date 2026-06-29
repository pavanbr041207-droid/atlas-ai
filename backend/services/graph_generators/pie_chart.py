"""services/graph_generators/pie_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config     = config or {}
    title      = config.get("title", "Pie Chart")
    label_col  = config.get("label_col")
    value_col  = config.get("value_col")
    donut      = config.get("donut", False)
    threshold  = config.get("threshold", 0.02)   # < 2% → grouped as "Other"

    if df is None or df.empty:
        return error_result("No data provided.")

    cat_cols = df.select_dtypes(exclude="number").columns.tolist()
    num_cols = df.select_dtypes(include="number").columns.tolist()

    if not label_col:
        label_col = cat_cols[0] if cat_cols else df.columns[0]
    if not value_col:
        value_col = num_cols[0] if num_cols else (df.columns[1] if len(df.columns) > 1 else None)
    if not value_col:
        return error_result("Need a numeric column for values.")

    labels = df[label_col].astype(str).tolist()
    values = pd.to_numeric(df[value_col], errors="coerce").fillna(0).tolist()

    # Group tiny slices
    total  = sum(values)
    merged_labels, merged_vals, other_val = [], [], 0
    for l, v in zip(labels, values):
        if total > 0 and v / total < threshold:
            other_val += v
        else:
            merged_labels.append(l)
            merged_vals.append(v)
    if other_val > 0:
        merged_labels.append("Other")
        merged_vals.append(other_val)

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    wedge_props = {"linewidth": 1.2, "edgecolor": "white"}
    wedges, texts, autotexts = ax.pie(
        merged_vals,
        labels=merged_labels,
        colors=PALETTE[:len(merged_vals)],
        autopct="%1.1f%%",
        startangle=140,
        wedgeprops=wedge_props,
        pctdistance=0.82,
    )
    for at in autotexts:
        at.set_fontsize(9)

    if donut:
        centre = plt.Circle((0, 0), 0.55, fc="white")
        ax.add_patch(centre)

    ax.set_title(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    url = save_fig(fig, "pie")
    return ok_result(url, f"Pie chart of {value_col} by {label_col}.")
