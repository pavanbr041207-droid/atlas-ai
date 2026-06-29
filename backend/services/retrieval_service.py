"""
services/retrieval_service.py
Cross-document keyword retrieval across all workspace files.
Fallback retrieval when vector_memory is unavailable.
"""
import re
import os


def search_workspace(query: str, session_id: str, top_k: int = 3) -> str:
    """
    Search across all files registered in workspace.
    Returns formatted context string for LLM injection.
    """
    # Try vector_memory first (existing system)
    try:
        from services.vector_memory import retrieve_as_context
        vm_ctx = retrieve_as_context(query, namespace=session_id, top_k=top_k)
        if vm_ctx and len(vm_ctx) > 50:
            return vm_ctx
    except Exception:
        pass

    # Fallback: keyword search across workspace retrieval indexes
    try:
        from services.workspace_manager import get_workspace
        ws      = get_workspace(session_id)
        indexes = ws.get("retrieval_indexes", {})
    except Exception:
        return ""

    all_chunks = []
    for file_id, chunks in indexes.items():
        if isinstance(chunks, list):
            all_chunks.extend(chunks)

    if not all_chunks:
        return ""

    query_terms = set(re.findall(r"\b\w{3,}\b", query.lower()))
    scored = []
    for chunk in all_chunks:
        text  = chunk.get("text", "").lower()
        score = sum(1 for t in query_terms if t in text)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    parts = []
    for score, chunk in scored[:top_k]:
        fname = chunk.get("filename", "")
        text  = chunk.get("text", "")[:400]
        parts.append(f"[{fname}]: {text}")

    return "\n\n".join(parts)


def keyword_search(query: str, text: str, window: int = 300) -> list:
    """Find relevant passages in text by keyword matching."""
    terms      = re.findall(r"\b\w{4,}\b", query.lower())
    text_lower = text.lower()
    results    = []

    for term in terms:
        start = 0
        while True:
            idx = text_lower.find(term, start)
            if idx == -1:
                break
            snippet_start = max(0, idx - 100)
            snippet_end   = min(len(text), idx + window)
            results.append(text[snippet_start:snippet_end].strip())
            start = idx + 1
            if len(results) >= 5:
                break

    return results[:5]


def get_document_text(session_id: str, file_id: str = None) -> str:
    """Get stored text of active document or specific file."""
    try:
        from services.workspace_manager import get_workspace, get_active_document_info
        ws = get_workspace(session_id)

        if file_id:
            finfo = ws.get("registered_files", {}).get(file_id, {})
        else:
            finfo = get_active_document_info(session_id) or {}

        return (finfo.get("full_text") or finfo.get("text") or
                finfo.get("profile", {}).get("summary", ""))
    except Exception:
        return ""
