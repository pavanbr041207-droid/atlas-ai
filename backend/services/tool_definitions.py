"""
services/tool_definitions.py
Tool schemas for Anthropic and OpenAI providers.
Covers: map generation, dataset query, and all 16 analytical graph types.
"""

def _graph_tool_anthropic(name, description):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Pass the original user message verbatim."
                },
                "title": {
                    "type": "string",
                    "description": "Optional chart title."
                }
            },
            "required": ["intent"]
        }
    }


def _graph_tool_openai(name, description):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Pass the original user message verbatim."
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional chart title."
                    }
                },
                "required": ["intent"]
            }
        }
    }


_GRAPH_DEFS = [
    ("generate_bar_graph",          "Generate a bar graph or column chart to compare values across categories."),
    ("generate_line_graph",         "Generate a line graph to show trends or changes over time."),
    ("generate_pie_chart",          "Generate a pie or donut chart to show parts of a whole."),
    ("generate_histogram",          "Generate a histogram to show frequency distribution of a numeric column."),
    ("generate_scatter_plot",       "Generate a scatter plot to show relationship between two numeric variables."),
    ("generate_area_graph",         "Generate an area graph, similar to a line graph but with filled area."),
    ("generate_bubble_chart",       "Generate a bubble chart where bubble size represents a third variable."),
    ("generate_box_plot",           "Generate a box-and-whisker plot to show distribution, median and outliers."),
    ("generate_radar_chart",        "Generate a radar or spider chart to compare multiple variables."),
    ("generate_waterfall_chart",    "Generate a waterfall chart to show cumulative effect of positive and negative values."),
    ("generate_pareto_chart",       "Generate a Pareto chart: bar graph with cumulative percentage line."),
    ("generate_candlestick_chart",  "Generate a candlestick chart for stock market OHLC price data."),
    ("generate_gantt_chart",        "Generate a Gantt chart to show project schedules and task timelines."),
    ("generate_dot_plot",           "Generate a dot plot to represent values as dots along an axis."),
    ("generate_treemap",            "Generate a treemap to display hierarchical data as nested rectangles."),
    ("generate_heatmap",            "Generate a heatmap using color intensity to show data values in a matrix."),
]

_MAP_DEFS_ANTHROPIC = [
    {
        "name": "generate_choropleth_map",
        "description": "Generate a choropleth district map for geographic/regional data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "description": "Pass the original user message verbatim."}
            },
            "required": ["intent"]
        }
    },
    {
        "name": "query_dataset",
        "description": "Query or analyze an uploaded dataset for statistics, counts, summaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The data query or analysis request."}
            },
            "required": ["query"]
        }
    }
]

_MAP_DEFS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "generate_choropleth_map",
            "description": "Generate a choropleth district map for geographic/regional data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "description": "Pass the original user message verbatim."}
                },
                "required": ["intent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_dataset",
            "description": "Query or analyze an uploaded dataset for statistics, counts, summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The data query or analysis request."}
                },
                "required": ["query"]
            }
        }
    }
]

# ── Final lists ───────────────────────────────────────────────────────────────
ATLAS_TOOLS_ANTHROPIC = _MAP_DEFS_ANTHROPIC + [
    _graph_tool_anthropic(name, desc) for name, desc in _GRAPH_DEFS
]

ATLAS_TOOLS_OPENAI = _MAP_DEFS_OPENAI + [
    _graph_tool_openai(name, desc) for name, desc in _GRAPH_DEFS
]

# Ollama: same as OpenAI format
ATLAS_TOOLS_OLLAMA = ATLAS_TOOLS_OPENAI
