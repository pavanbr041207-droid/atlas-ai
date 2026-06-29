"""
services/graph_dispatcher.py
Routes tool_name → correct graph generator.
Handles keyword-based fallback detection for Ollama (no tool calling).
"""
import re
import pandas as pd


# ── Tool name → generator module ─────────────────────────────────────────────
GRAPH_TOOL_MAP = {
    "generate_bar_graph":       "services.graph_generators.bar_graph",
    "generate_line_graph":      "services.graph_generators.line_graph",
    "generate_pie_chart":       "services.graph_generators.pie_chart",
    "generate_histogram":       "services.graph_generators.histogram",
    "generate_scatter_plot":    "services.graph_generators.scatter_plot",
    "generate_area_graph":      "services.graph_generators.area_graph",
    "generate_bubble_chart":    "services.graph_generators.bubble_chart",
    "generate_box_plot":        "services.graph_generators.box_plot",
    "generate_radar_chart":     "services.graph_generators.radar_chart",
    "generate_waterfall_chart": "services.graph_generators.waterfall_chart",
    "generate_pareto_chart":    "services.graph_generators.pareto_chart",
    "generate_candlestick_chart": "services.graph_generators.candlestick_chart",
    "generate_gantt_chart":     "services.graph_generators.gantt_chart",
    "generate_dot_plot":        "services.graph_generators.dot_plot",
    "generate_treemap":         "services.graph_generators.treemap",
    "generate_heatmap":         "services.graph_generators.heatmap",
}

# ── Keyword-based fallback detection (used when LLM = Ollama) ─────────────────
_KEYWORDS = {
    "generate_bar_graph":       ["bar graph", "bar chart", "column chart", "barchart"],
    "generate_line_graph":      ["line graph", "line chart", "trend line", "linechart"],
    "generate_pie_chart":       ["pie chart", "pie graph", "donut chart", "donut graph"],
    "generate_histogram":       ["histogram", "frequency distribution", "freq dist"],
    "generate_scatter_plot":    ["scatter plot", "scatter graph", "scatterplot", "scatter chart"],
    "generate_area_graph":      ["area graph", "area chart", "stacked area"],
    "generate_bubble_chart":    ["bubble chart", "bubble graph", "bubble plot"],
    "generate_box_plot":        ["box plot", "box-and-whisker", "boxplot", "whisker"],
    "generate_radar_chart":     ["radar chart", "spider chart", "radar graph", "spider graph", "web chart"],
    "generate_waterfall_chart": ["waterfall chart", "waterfall graph", "bridge chart"],
    "generate_pareto_chart":    ["pareto chart", "pareto graph", "pareto analysis"],
    "generate_candlestick_chart": ["candlestick", "candle chart", "ohlc", "stock chart"],
    "generate_gantt_chart":     ["gantt chart", "gantt graph", "project timeline", "timeline chart"],
    "generate_dot_plot":        ["dot plot", "dot chart", "cleveland dot"],
    "generate_treemap":         ["treemap", "tree map", "tree chart"],
    "generate_heatmap":         ["heat map", "heatmap", "correlation matrix", "correlation heatmap"],
}


def detect_graph_intent(message: str) -> str | None:
    """
    Keyword-based graph type detection.
    Returns tool_name or None.
    """
    msg = message.lower()
    for tool_name, keywords in _KEYWORDS.items():
        for kw in keywords:
            if kw in msg:
                return tool_name
    return None


def is_graph_request(message: str) -> bool:
    """Quick check: does message look like a graph generation request?"""
    return detect_graph_intent(message) is not None


def dispatch(tool_name: str, df: pd.DataFrame, config: dict = None) -> dict:
    """
    Call the correct generator for tool_name.
    Returns {"status": "ok", "image_url": ..., "description": ...}
         or {"status": "error", "message": ...}
    """
    if tool_name not in GRAPH_TOOL_MAP:
        return {"status": "error", "message": f"Unknown graph tool: {tool_name}"}

    module_path = GRAPH_TOOL_MAP[tool_name]
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return mod.generate(df, config or {})
    except ImportError as e:
        return {"status": "error", "message": f"Graph module not loaded: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Graph generation error: {e}"}


def all_tool_names() -> list:
    return list(GRAPH_TOOL_MAP.keys())
