"""services/graph_generators/gantt_chart.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Gantt Chart")
    task_col  = config.get("task_col")
    start_col = config.get("start_col")
    end_col   = config.get("end_col")
    group_col = config.get("group_col")   # optional colour grouping

    if df is None or df.empty:
        return error_result("No data provided.")

    cols_lower = {c.lower(): c for c in df.columns}

    if not task_col:
        for c in ["task", "name", "activity", "item"]:
            if c in cols_lower:
                task_col = cols_lower[c]; break
        if not task_col:
            task_col = df.columns[0]

    if not start_col:
        for c in ["start", "begin", "from", "start_date"]:
            if c in cols_lower:
                start_col = cols_lower[c]; break

    if not end_col:
        for c in ["end", "finish", "to", "end_date", "due"]:
            if c in cols_lower:
                end_col = cols_lower[c]; break

    if not start_col or not end_col:
        num_cols = df.select_dtypes(include="number").columns.tolist()
        if len(num_cols) >= 2:
            start_col = start_col or num_cols[0]
            end_col   = end_col   or num_cols[1]
        else:
            return error_result(
                "Gantt chart needs start and end columns.\n"
                "Expected columns: task, start, end (numeric days or dates)."
            )

    tasks   = df[task_col].astype(str).tolist()
    try:
        starts = pd.to_numeric(df[start_col], errors="coerce").fillna(0).tolist()
        ends   = pd.to_numeric(df[end_col],   errors="coerce").fillna(0).tolist()
    except Exception as e:
        return error_result(f"Could not parse start/end columns: {e}")

    groups = df[group_col].astype(str).tolist() if group_col and group_col in df.columns else None
    unique_groups = list(dict.fromkeys(groups)) if groups else []
    color_map     = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(unique_groups)}

    h = max(5, len(tasks) * 0.5)
    fig, ax = plt.subplots(figsize=(FIG_W, h))

    for i, (task, s, e) in enumerate(zip(tasks, starts, ends)):
        dur   = max(e - s, 0.1)
        color = color_map.get(groups[i], PALETTE[0]) if groups else PALETTE[i % len(PALETTE)]
        ax.barh(i, dur, left=s, height=0.55, color=color, edgecolor="white", linewidth=0.6)
        ax.text(s + dur / 2, i, f" {e - s:.0f}d", va="center", ha="center",
                fontsize=8, color="white", fontweight="bold")

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels(tasks, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Time (days / units)")
    ax.set_title(title, fontsize=14, fontweight="bold")

    if unique_groups:
        patches = [mpatches.Patch(color=color_map[g], label=g) for g in unique_groups]
        ax.legend(handles=patches, loc="lower right", fontsize=8)

    plt.tight_layout()
    url = save_fig(fig, "gantt")
    return ok_result(url, f"Gantt chart of {len(tasks)} tasks.")
