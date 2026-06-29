"""
services/workspace_manager.py
Central workspace memory for Atlas AI.
Persists uploaded files, active context, analysis history per session.
Independent of chat memory — stores files, not dialogue.
"""
import os
from utils.storage import storage_path, read_json, write_json, now, new_id

STORAGE = storage_path()


def _ws_path(session_id: str) -> str:
    d = os.path.join(STORAGE, "workspaces")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{session_id}.json")


def get_workspace(session_id: str) -> dict:
    """Get full workspace for session."""
    return read_json(_ws_path(session_id), {
        "session_id":       session_id,
        "registered_files": {},
        "active_file":      None,
        "active_document":  None,
        "active_dataset":   None,
        "active_sheet":     None,
        "active_columns":   [],
        "active_statistics":{},
        "generated_maps":   [],
        "generated_charts": [],
        "analysis_history": [],
        "execution_history":[],
        "retrieval_indexes":{},
        "created":          now(),
        "updated":          now(),
    })


def _save(session_id: str, ws: dict):
    ws["updated"] = now()
    write_json(_ws_path(session_id), ws)


def register_file(session_id: str, file_id: str, file_info: dict) -> dict:
    """
    Register uploaded file in workspace. Auto-sets as active_file.
    file_info: {name, path, type, profile}
    """
    if not session_id:
        return {}
    ws = get_workspace(session_id)
    ws["registered_files"][file_id] = {
        **file_info,
        "file_id":    file_id,
        "registered": now(),
    }
    ws["active_file"] = file_id

    ftype = file_info.get("type", "")
    # Tabular data types
    if ftype in ("excel", "csv", "xlsx", "xls", "json"):
        ws["active_dataset"] = file_id
        profile = file_info.get("profile", {})
        ws["active_columns"]    = profile.get("columns", [])
        ws["active_statistics"] = profile.get("statistics", {})
    # Document types
    elif ftype in ("pdf", "docx", "pptx", "text", "txt", "md"):
        ws["active_document"] = file_id

    _save(session_id, ws)
    return ws


def get_active_file_info(session_id: str) -> dict | None:
    ws = get_workspace(session_id)
    fid = ws.get("active_file")
    if not fid:
        return None
    return ws["registered_files"].get(fid)


def get_active_dataset_info(session_id: str) -> dict | None:
    ws = get_workspace(session_id)
    fid = ws.get("active_dataset")
    if not fid:
        return None
    return ws["registered_files"].get(fid)


def get_active_document_info(session_id: str) -> dict | None:
    ws = get_workspace(session_id)
    fid = ws.get("active_document")
    if not fid:
        return None
    return ws["registered_files"].get(fid)


def get_all_files(session_id: str) -> list:
    ws = get_workspace(session_id)
    return list(ws.get("registered_files", {}).values())


def get_file_count(session_id: str) -> int:
    ws = get_workspace(session_id)
    return len(ws.get("registered_files", {}))


def log_analysis(session_id: str, query: str, result: str):
    """Log executed analysis to history."""
    ws = get_workspace(session_id)
    history = ws.get("analysis_history", [])
    history.insert(0, {"query": query[:120], "result": str(result)[:400], "time": now()})
    ws["analysis_history"] = history[:20]
    _save(session_id, ws)


def log_execution(session_id: str, operation: str, result: str):
    ws = get_workspace(session_id)
    history = ws.get("execution_history", [])
    history.insert(0, {"operation": operation, "result": str(result)[:300], "time": now()})
    ws["execution_history"] = history[:20]
    _save(session_id, ws)


def add_map(session_id: str, map_id: str, title: str):
    ws = get_workspace(session_id)
    maps = ws.get("generated_maps", [])
    maps.insert(0, {"map_id": map_id, "title": title, "time": now()})
    ws["generated_maps"] = maps[:10]
    _save(session_id, ws)


def set_retrieval_index(session_id: str, file_id: str, chunks: list):
    ws = get_workspace(session_id)
    ws["retrieval_indexes"][file_id] = chunks
    _save(session_id, ws)


def clear_workspace(session_id: str):
    path = _ws_path(session_id)
    if os.path.exists(path):
        os.remove(path)


def resolve_file_for_query(session_id: str, query: str) -> dict | None:
    """
    Intelligently resolve which file to use.
    Single file → always use it. Multiple → match by name mention or use active.
    """
    ws    = get_workspace(session_id)
    files = ws.get("registered_files", {})
    if not files:
        return None
    if len(files) == 1:
        return list(files.values())[0]

    query_lower = query.lower()
    for fid, finfo in files.items():
        fname = finfo.get("name", "").lower()
        stem  = os.path.splitext(fname)[0].lower()
        if stem in query_lower or fname in query_lower:
            return finfo

    # Default: active_file
    active_id = ws.get("active_file")
    if active_id and active_id in files:
        return files[active_id]
    return list(files.values())[-1]
