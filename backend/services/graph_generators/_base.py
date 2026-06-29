"""_base.py — shared utilities for all graph generators."""
import os, uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
GRAPHS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "storage", "graphs"))
os.makedirs(GRAPHS_DIR, exist_ok=True)

STYLE      = "seaborn-v0_8-whitegrid"
PALETTE    = ["#4C72B0","#DD8452","#55A868","#C44E52","#8172B2",
              "#937860","#DA8BC3","#8C8C8C","#CCB974","#64B5CD"]
FIG_W, FIG_H = 11, 6
DPI          = 150


def save_fig(fig, prefix: str) -> str:
    """Save figure, return URL path."""
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    path  = os.path.join(GRAPHS_DIR, fname)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"/storage/graphs/{fname}"


def apply_style():
    try:
        plt.style.use(STYLE)
    except Exception:
        plt.style.use("ggplot")


def error_result(msg: str) -> dict:
    return {"status": "error", "message": msg}


def ok_result(url: str, description: str) -> dict:
    return {"status": "ok", "image_url": url, "description": description}
