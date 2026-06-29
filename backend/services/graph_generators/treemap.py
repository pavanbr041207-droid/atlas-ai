"""services/graph_generators/treemap.py — uses squarify if available, fallback to matplotlib"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.cm as cm
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, PALETTE, FIG_W, FIG_H


def _squarify_layout(values, x, y, w, h):
    """Minimal squarify implementation — no external dependency."""
    if not values:
        return []
    total = sum(values)
    if total == 0:
        return []
    rects = []
    _layout(sorted(values, reverse=True), x, y, w, h, total, rects)
    return rects


def _layout(values, x, y, w, h, total, rects):
    if not values:
        return
    if len(values) == 1:
        rects.append((x, y, w, h, values[0]))
        return
    # Split horizontally or vertically based on aspect ratio
    split_idx = 1
    best_ratio = float("inf")
    row_sum = 0
    for i, v in enumerate(values):
        row_sum += v
        if w >= h:
            row_h = row_sum / total * h
            ratio = max(v / total * h / row_h, row_h / (v / total * h + 1e-9))
        else:
            row_w = row_sum / total * w
            ratio = max(v / total * w / row_w, row_w / (v / total * w + 1e-9))
        if ratio < best_ratio:
            best_ratio = ratio
            split_idx  = i + 1

    row_vals  = values[:split_idx]
    rest_vals = values[split_idx:]
    row_sum   = sum(row_vals)

    if w >= h:
        row_w = row_sum / total * w
        cy = y
        for v in row_vals:
            rh = v / row_sum * h
            rects.append((x, cy, row_w, rh, v))
            cy += rh
        if rest_vals:
            _layout(rest_vals, x + row_w, y, w - row_w, h, total - row_sum, rects)
    else:
        row_h = row_sum / total * h
        cx = x
        for v in row_vals:
            rw = v / row_sum * w
            rects.append((cx, y, rw, row_h, v))
            cx += rw
        if rest_vals:
            _layout(rest_vals, x, y + row_h, w, h - row_h, total - row_sum, rects)


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Treemap")
    label_col = config.get("label_col")
    value_col = config.get("value_col")

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
    values = [max(v, 0) for v in values]
    if sum(values) == 0:
        return error_result("All values are zero — cannot render treemap.")

    # Try squarify first
    try:
        import squarify
        normed = squarify.normalize_sizes(values, 100, 100)
        rects  = squarify.squarify(normed, 0, 0, 100, 100)
        use_squarify = True
    except ImportError:
        rects = _squarify_layout(values, 0, 0, 100, 100)
        use_squarify = False

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    cmap    = cm.get_cmap("tab20", len(labels))
    total   = sum(values)

    if use_squarify:
        for i, (r, lbl, val) in enumerate(zip(rects, labels, values)):
            rx, ry, rw, rh = r["x"], r["y"], r["dx"], r["dy"]
            color = cmap(i)
            ax.add_patch(mpatches.FancyBboxPatch(
                (rx + 0.2, ry + 0.2), rw - 0.4, rh - 0.4,
                boxstyle="round,pad=0.3", facecolor=color, edgecolor="white", lw=1.5
            ))
            pct = val / total * 100
            if rw > 5 and rh > 4:
                ax.text(rx + rw / 2, ry + rh / 2 + 1, lbl, ha="center", va="center",
                        fontsize=min(9, rw * 0.9), fontweight="bold", color="white",
                        wrap=True)
                ax.text(rx + rw / 2, ry + rh / 2 - 2, f"{pct:.1f}%", ha="center",
                        va="center", fontsize=min(8, rw * 0.7), color="white", alpha=0.9)
    else:
        for i, (r, lbl, val) in enumerate(zip(rects, labels, values)):
            rx, ry, rw, rh, _ = r
            color = cmap(i)
            ax.add_patch(mpatches.FancyBboxPatch(
                (rx + 0.2, ry + 0.2), rw - 0.4, rh - 0.4,
                boxstyle="round,pad=0.3", facecolor=color, edgecolor="white", lw=1.5
            ))
            pct = val / total * 100
            if rw > 5 and rh > 4:
                ax.text(rx + rw / 2, ry + rh / 2 + 1, lbl, ha="center", va="center",
                        fontsize=min(9, rw * 0.9), fontweight="bold", color="white")
                ax.text(rx + rw / 2, ry + rh / 2 - 2, f"{pct:.1f}%", ha="center",
                        va="center", fontsize=min(8, rw * 0.7), color="white", alpha=0.9)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    plt.tight_layout()
    url = save_fig(fig, "treemap")
    return ok_result(url, f"Treemap of {value_col} by {label_col}.")
