"""
services/command_router.py
Classify user commands into operation types for workspace-aware routing.

Operation types:
  DATA_OPERATION      → pandas tool-first execution
  DOCUMENT_OPERATION  → document text retrieval + LLM explanation
  MAP_OPERATION       → geo dataset + choropleth pipeline
  CHART_OPERATION     → chart/graph generation
  SEARCH_OPERATION    → cross-file retrieval
  NORMAL_CHAT         → LLM with workspace context

Rule: MAP_OPERATION is detected separately in chat_routes.py.
      This router focuses on DATA_OPERATION vs DOCUMENT_OPERATION vs others.
"""
import re

# ── DATA OPERATION patterns ───────────────────────────────────────────────────
_DATA = [
    r"\b(count|how many|total number of|number of)\b.*(district|state|region|row|record|entry|unique|taluk|area|city)\b",
    r"\b(count|how many)\b",
    r"\b(list|show all|display all|show me all|print all)\b.*(district|state|name|value|row|entry|region)\b",
    r"\bwhat are the\b.*(district|state|name|column|field|value)\b",
    r"\b(maximum|minimum|highest|lowest|largest|smallest|most|least|max|min)\b.*(district|value|row|state|region)\b",
    r"\bwhich\b.*(district|state|region|area)\b.*(has|have|is|are)\b.*(highest|lowest|maximum|minimum|most|least)\b",
    r"\b(average|mean|median|sum|total|combined)\b.*(of|the|for)?\b",
    r"\b(describe|statistics|stats|summary|profile)\b.*(dataset|data|file|csv|table)\b",
    r"\btop\s+\d+\b",
    r"\bbottom\s+\d+\b",
    r"\brank\b.*(by|the|district|value)\b",
    r"\b(columns?|fields?|schema|headers?|structure)\b.*(dataset|file|csv|data)\b",
    r"\bshow\b.*(dataset|table|data|all)\b",
    r"\bhow big\b|\bshape of\b|\bsize of\b",
    r"\brows?\b.*(dataset|file|csv|data|count)\b",
    r"\bdistrict\b.*(count|list|name|all)\b",
    r"\b(count|list|show|find)\b.*(all\s+)?(district|state|region)\b",
    # Groupby / aggregate
    r"\bby\s+(district|state|region|taluk|city|gender|category|type|year|month)\b",
    r"\b(group\s*by|grouped\s*by|breakdown|per\s+district|per\s+state)\b",
    r"\b(count|sum|average|total)\s+\w+\s+by\b",
    # Duplicates + data quality
    r"\b(duplicate|duplicates|repeated|repeating|double entries)\b",
    # Normalize / clean
    r"\b(normalize|normalise|fix\s+spelling|clean\s+data|correct\s+names?|standardize|standardise)\b",
]

# ── DOCUMENT OPERATION patterns ───────────────────────────────────────────────
_DOC = [
    r"\b(summarize|summarise)\b.*(document|pdf|file|report|paper|article)\b",
    r"\bwhat.*(document|pdf|file|report)\b.*(say|about|contain|discuss)\b",
    r"\b(explain|describe|read|analyse|analyze)\b.*(document|pdf|file|report)\b",
    r"\bgive me (a\s+)?(summary|overview|abstract|gist)\b",
    r"\b(key|main|important|critical)\b.*(point|finding|section|insight|takeaway)\b",
    r"\bwhat (is|are)\b.*(in the|the)\b.*(document|pdf|report|paper)\b",
    r"\bextract\b.*(information|data|text|content)\b.*(from|in)\b",
    r"\btopics?\b.*(covered|discussed|mentioned)\b",
]

# ── SEARCH OPERATION patterns ─────────────────────────────────────────────────
_SEARCH = [
    r"\b(search|find|look up|retrieve)\b.*(in|from|across|within)\b.*(file|document|upload|workspace)\b",
    r"\b(find|search)\b.*(information|details|data)\b.*(about|regarding|on)\b",
]

# ── CHART OPERATION patterns ──────────────────────────────────────────────────
_CHART = [
    r"\b(create|generate|make|draw|plot|show)\b.*(bar|pie|line|scatter|histogram|area)\b.*(chart|graph|plot)?\b",
    r"\b(bar|pie|line|scatter|histogram|area)\b.*(chart|graph|plot)\b",
    r"\bplot\b.*(the|this|data)\b",
    r"\bvisuali[sz]e\b.*(as|into)?\b.*(chart|graph|bar|pie|line)\b",
]

# ── IMPLICIT DATA patterns (weaker signal — only trigger if dataset active) ───
_IMPLICIT_DATA = [
    r"^count\b",
    r"^how many\b",
    r"^list\b",
    r"^show\b",
    r"^what are\b",
    r"\bdistrict\b",
    r"\bcolumn\b",
    r"\brow\b",
    r"\bvalue\b",
    r"^find\b",
    r"^give me\b.*(list|names)\b",
]


def classify(user_msg: str, workspace: dict) -> dict:
    """
    Classify user command into operation type.
    Returns: {op_type, confidence}
    """
    msg = user_msg.lower().strip()

    has_dataset  = bool(workspace.get("active_dataset"))
    has_document = bool(workspace.get("active_document"))
    has_file     = bool(workspace.get("active_file"))

    # ── Strong DATA patterns (always high confidence if match) ────────────
    for p in _DATA:
        if re.search(p, msg):
            return {"op_type": "DATA_OPERATION", "confidence": 0.92}

    # ── CHART patterns ─────────────────────────────────────────────────────
    for p in _CHART:
        if re.search(p, msg):
            return {"op_type": "CHART_OPERATION", "confidence": 0.88}

    # ── DOCUMENT patterns (only if document active) ───────────────────────
    if has_document:
        for p in _DOC:
            if re.search(p, msg):
                return {"op_type": "DOCUMENT_OPERATION", "confidence": 0.85}

    # ── SEARCH patterns ────────────────────────────────────────────────────
    for p in _SEARCH:
        if re.search(p, msg):
            return {"op_type": "SEARCH_OPERATION", "confidence": 0.80}

    # ── Implicit DATA (only if active dataset present) ────────────────────
    if has_dataset:
        for p in _IMPLICIT_DATA:
            if re.search(p, msg):
                return {"op_type": "DATA_OPERATION", "confidence": 0.70}

    return {"op_type": "NORMAL_CHAT", "confidence": 0.60}


def build_tool_result_prefix(op_type: str, result: dict) -> str:
    """
    Build system injection that tells LLM the backend already computed the answer.
    Forces LLM to explain the exact pre-computed result — never recompute.
    """
    if not result.get("executed"):
        return ""

    result_text = result.get("result_text", "")
    operation   = result.get("operation", "")

    lines = [
        f"\n[BACKEND TOOL EXECUTED: {op_type} — {operation}]",
        f"Computed result: {result_text}",
        "INSTRUCTION: Use this exact result in your response.",
        "Do NOT recompute, estimate, or guess. The backend already ran the query.",
        "Explain the result naturally to the user.\n",
    ]
    return "\n".join(lines) + "\n"
