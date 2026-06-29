"""services/graph_generators/candlestick_chart.py — pure matplotlib, no mplfinance required"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np
from ._base import apply_style, save_fig, error_result, ok_result, FIG_W, FIG_H


def generate(df: pd.DataFrame, config: dict = None) -> dict:
    config    = config or {}
    title     = config.get("title", "Candlestick Chart")
    date_col  = config.get("date_col")
    open_col  = config.get("open_col")
    high_col  = config.get("high_col")
    low_col   = config.get("low_col")
    close_col = config.get("close_col")

    if df is None or df.empty:
        return error_result("No data provided.")

    # Auto-detect OHLC columns
    cols_lower = {c.lower(): c for c in df.columns}
    if not date_col:
        for candidate in ["date", "time", "period", "day"]:
            if candidate in cols_lower:
                date_col = cols_lower[candidate]
                break
        if not date_col:
            date_col = df.columns[0]

    for attr, candidates in [
        ("open_col",  ["open", "o"]),
        ("high_col",  ["high", "h"]),
        ("low_col",   ["low",  "l"]),
        ("close_col", ["close","c"]),
    ]:
        if not locals()[attr]:
            for c in candidates:
                if c in cols_lower:
                    locals_ref = {attr: cols_lower[c]}
                    if attr == "open_col":  open_col  = cols_lower[c]
                    if attr == "high_col":  high_col  = cols_lower[c]
                    if attr == "low_col":   low_col   = cols_lower[c]
                    if attr == "close_col": close_col = cols_lower[c]
                    break

    num_cols = df.select_dtypes(include="number").columns.tolist()
    if len(num_cols) < 4:
        return error_result(
            "Candlestick needs 4 numeric columns: Open, High, Low, Close.\n"
            "Expected columns: date, open, high, low, close"
        )

    # Fall back to positional
    if not open_col:  open_col  = num_cols[0]
    if not high_col:  high_col  = num_cols[1]
    if not low_col:   low_col   = num_cols[2]
    if not close_col: close_col = num_cols[3]

    try:
        opens  = pd.to_numeric(df[open_col],  errors="coerce").values
        highs  = pd.to_numeric(df[high_col],  errors="coerce").values
        lows   = pd.to_numeric(df[low_col],   errors="coerce").values
        closes = pd.to_numeric(df[close_col], errors="coerce").values
        dates  = df[date_col].astype(str).tolist()
    except Exception as e:
        return error_result(f"Could not read OHLC data: {e}")

    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    w = 0.4
    for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes)):
        color = "#4CAF50" if c >= o else "#F44336"
        # Wick
        ax.plot([i, i], [l, h], color=color, lw=1.2)
        # Body
        body_lo = min(o, c)
        body_hi = max(o, c)
        ax.add_patch(mpatches.FancyBboxPatch(
            (i - w / 2, body_lo), w, body_hi - body_lo,
            boxstyle="square,pad=0",
            linewidth=0.5, edgecolor=color, facecolor=color, alpha=0.85
        ))

    tick_step = max(1, len(dates) // 10)
    ax.set_xticks(range(0, len(dates), tick_step))
    ax.set_xticklabels(dates[::tick_step], rotation=35, ha="right", fontsize=8)
    ax.set_xlim(-0.6, len(dates) - 0.4)
    ax.set_ylabel("Price")
    ax.set_title(title, fontsize=14, fontweight="bold")

    up_patch   = mpatches.Patch(color="#4CAF50", label="Bullish")
    down_patch = mpatches.Patch(color="#F44336", label="Bearish")
    ax.legend(handles=[up_patch, down_patch], fontsize=9)
    plt.tight_layout()
    url = save_fig(fig, "candlestick")
    return ok_result(url, f"Candlestick chart ({open_col}/{high_col}/{low_col}/{close_col}).")
