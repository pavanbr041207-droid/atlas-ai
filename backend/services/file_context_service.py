"""
services/file_context_service.py
Build workspace context strings for LLM injection.
Ensures every LLM request knows what files are active in the workspace.
"""
import os


def build_workspace_context(session_id: str, user_msg: str = "") -> str:
    """
    Build ACTIVE WORKSPACE block for injection into LLM system prompt.
    Returns formatted context string, or "" if no workspace files.
    """
    try:
        from services.workspace_manager import get_workspace
        ws = get_workspace(session_id)
    except Exception:
        return ""

    files = ws.get("registered_files", {})

    # Also check session_state for dataset info (backward compat)
    has_session_ds = False
    session_ds     = {}
    try:
        from services.session_state import get_latest_dataset
        session_ds    = get_latest_dataset(session_id) or {}
        has_session_ds = bool(session_ds.get("csv_path") and
                              os.path.exists(session_ds.get("csv_path", "")))
    except Exception:
        pass

    if not files and not has_session_ds:
        return ""

    lines = ["\n=== ACTIVE WORKSPACE ==="]

    if files:
        lines.append(f"Files registered: {len(files)}")

    # Active dataset info
    active_ds_id = ws.get("active_dataset")
    ds_info      = {}
    if active_ds_id and active_ds_id in files:
        ds_info = files[active_ds_id]

    # If no workspace dataset but session_state has one, use that
    if not ds_info and has_session_ds:
        ds_info = {
            "name":    session_ds.get("filename", "active_dataset.csv"),
            "type":    "excel",
            "profile": {
                "rows":      session_ds.get("rows", 0),
                "columns":   session_ds.get("columns", []),
                "geo_col":   session_ds.get("geo_col"),
                "value_col": session_ds.get("value_col"),
                "geo_scope": session_ds.get("geo_scope", ""),
                "file_path": session_ds.get("csv_path"),
            }
        }

    if ds_info:
        profile  = ds_info.get("profile", {})
        fname    = ds_info.get("name", "")
        rows     = profile.get("rows", 0)
        cols     = profile.get("columns", [])
        geo_col  = profile.get("geo_col")
        val_col  = profile.get("value_col")
        geo_vals = profile.get("geo_values", [])
        stats    = profile.get("statistics", {})
        preview  = profile.get("preview", "")

        lines.append("")
        lines.append(f"Active Dataset: {fname}")
        if rows:
            lines.append(f"Rows: {rows}")
        if cols:
            lines.append(f"Columns: {', '.join(cols)}")
        if geo_col:
            lines.append(f"Geographic column: {geo_col}")
        if val_col:
            lines.append(f"Value column: {val_col}")
        if geo_vals:
            sample = geo_vals[:5]
            lines.append(f"Sample values ({geo_col}): {', '.join(str(v) for v in sample)}")
        if stats and val_col and val_col in stats:
            s = stats[val_col]
            lines.append(f"Value stats: min={s.get('min')}, max={s.get('max')}, mean={s.get('mean')}")
        if preview:
            lines.append(f"Data preview (first 5 rows):\n{preview[:600]}")

    # Active document info
    active_doc_id = ws.get("active_document")
    if active_doc_id and active_doc_id in files:
        doc     = files[active_doc_id]
        profile = doc.get("profile", {})
        lines.append("")
        lines.append(f"Active Document: {doc.get('name', '')}")
        if profile:
            lines.append(f"Type: {profile.get('type', '')}")
            words = profile.get("words", 0)
            if words:
                lines.append(f"Words: {words}")
            headings = profile.get("headings", [])
            if headings:
                lines.append(f"Sections: {', '.join(headings[:5])}")
            summary = profile.get("summary", "")
            if summary:
                lines.append(f"Summary: {summary[:250]}")

    # Recent analysis history
    history = ws.get("analysis_history", [])
    if history:
        lines.append("")
        lines.append("Recent queries answered:")
        for item in history[:3]:
            q = item.get("query", "")[:80]
            r = item.get("result", "")[:120]
            lines.append(f"  Q: {q} → Result: {r}")

    lines.append("=== END WORKSPACE ===\n")
    return "\n".join(lines)


def get_active_dataset_path(session_id: str) -> str | None:
    """
    Get file path of active dataset. Checks workspace first, then session_state.
    """
    # Try workspace active dataset
    try:
        from services.workspace_manager import get_active_dataset_info
        ds_info = get_active_dataset_info(session_id)
        if ds_info:
            profile = ds_info.get("profile", {})
            path = (profile.get("file_path") or ds_info.get("path") or "")
            if path and os.path.exists(path):
                return path
    except Exception:
        pass

    # Fall back to session_state (existing system)
    try:
        from services.session_state import get_latest_dataset
        ds = get_latest_dataset(session_id)
        if ds:
            path = ds.get("csv_path", "")
            if path and os.path.exists(path):
                return path
    except Exception:
        pass

    return None


def get_active_file_path(session_id: str) -> str | None:
    """Get file path of active file."""
    try:
        from services.workspace_manager import get_active_file_info
        finfo = get_active_file_info(session_id)
        if finfo:
            path = finfo.get("path") or finfo.get("profile", {}).get("file_path", "")
            if path and os.path.exists(path):
                return path
    except Exception:
        pass
    return None


def register_file_in_workspace(session_id: str, file_path: str, file_id: str,
                                filename: str, file_result: dict):
    """
    Helper to register any processed file in workspace.
    Called from file_routes and chat_routes after route_file().
    """
    if not session_id:
        return

    try:
        from services.workspace_manager import register_file, set_retrieval_index
        from services.file_router import get_file_type

        ftype   = get_file_type(filename)
        profile = {}

        if ftype == "excel":
            # Profile the tabular dataset
            try:
                from services.dataset_manager import profile_dataset
                profile = profile_dataset(file_path, filename, file_id)
                # Also store in session_state for backward compatibility
                if profile and not profile.get("error"):
                    try:
                        from services.session_state import store_dataset
                        store_dataset(session_id, {
                            "csv_path":  profile.get("file_path", file_path),
                            "filename":  filename,
                            "rows":      profile.get("rows", 0),
                            "columns":   profile.get("columns", []),
                            "geo_col":   profile.get("geo_col"),
                            "value_col": profile.get("value_col"),
                            "geo_scope": profile.get("geo_scope", "unknown"),
                            "label":     f"{filename} ({profile.get('rows',0)} rows)",
                        })
                    except Exception:
                        pass
            except Exception:
                pass

        elif ftype in ("pdf", "docx", "pptx", "text"):
            # Profile the document
            try:
                from services.document_intelligence import profile_document
                text = (file_result.get("text") or file_result.get("preview") or "")
                profile = profile_document(file_path, filename, file_id, ftype, text)
                # Store retrieval index
                if profile.get("chunks"):
                    set_retrieval_index(session_id, file_id, profile["chunks"])
            except Exception:
                pass

        file_info = {
            "name":      filename,
            "path":      file_path,
            "type":      ftype,
            "profile":   profile,
            "full_text": (file_result.get("text") or file_result.get("preview") or "")[:5000],
        }
        register_file(session_id, file_id, file_info)

    except Exception:
        pass  # Never crash the main flow
