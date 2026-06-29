"""
routes/chat_routes.py
Fully stateful ChatGPT-like pipeline:
  1. Context manager builds full prompt (history + summary + dataframe)
  2. Map intent? → check session dataframe FIRST → use it directly
  3. References previous data? → use session dataframe
  4. LLM response → response parser auto-detects structured data → saves CSV
  5. Permission gate before any map generation
  6. Project memory isolation
"""
import os
from flask import Blueprint, request, jsonify
from utils.llm import ask_llm, is_map_request, detect_color, clean_title, extract_data_from_llm, infer_topic_geography_metric, is_color_change_request
from utils.storage import storage_path, read_json, write_json, now, new_id
from utils.csv_handler import parse_pasted, save_csv


def _call_openai_vision(image_path: str, user_prompt: str, cfg: dict) -> str:
    """Send image to OpenAI vision API (gpt-4o supports vision)."""
    import base64
    from services.providers.provider_manager import get_api_key
    key = get_api_key("openai").strip()
    if not key:
        return "❌ OpenAI API key not set. Go to Settings to add it."
    try:
        import openai
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = image_path.rsplit(".", 1)[-1].lower()
        mime = {"jpg":"jpeg","jpeg":"jpeg","png":"png","webp":"webp","gif":"gif"}.get(ext,"png")
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=cfg.get("openai_model","gpt-4o"),
            messages=[{"role":"user","content":[
                {"type":"image_url","image_url":{"url":f"data:image/{mime};base64,{b64}"}},
                {"type":"text","text": user_prompt},
            ]}],
            max_tokens=cfg.get("max_tokens",1500),
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ OpenAI vision error: {e}"

chat_bp       = Blueprint("chat", __name__)
STORAGE       = storage_path()
chat_sessions = {}   # in-memory session messages cache

def chat_idx():     return os.path.join(STORAGE,"chats","_index.json")
def chat_file(cid): return os.path.join(STORAGE,"chats",f"{cid}.json")
def load_idx():     return read_json(chat_idx(),[])
def save_idx(d):    write_json(chat_idx(),d)

def upsert_idx(sid, name, project_id=None):
    idx = load_idx()
    for c in idx:
        if c["id"]==sid:
            c.update({"name":name,"project_id":project_id,"updated":now()})
            save_idx(idx); return
    idx.insert(0,{"id":sid,"name":name,"project_id":project_id,"created":now(),"updated":now()})
    save_idx(idx)


@chat_bp.route("/send", methods=["POST","OPTIONS"])
def send():
    if request.method == "OPTIONS": return jsonify({}), 200

    data             = request.json or {}
    user_msg         = data.get("message","")
    csv_path         = data.get("csv_path")
    pasted           = data.get("pasted_data")
    session_id       = data.get("session_id","default")
    session_name     = data.get("session_name","New Chat")
    project_id       = data.get("project_id")
    sidebar_cmap     = data.get("colormap","Blues")
    # File attached with this message (uploaded before send was clicked)
    attached_path    = data.get("attached_file_path")   # server path
    attached_type    = data.get("attached_file_type")   # image|pdf|excel|docx|text|csv
    attached_name    = data.get("attached_file_name","file")

    uploads_dir = os.path.join(STORAGE,"uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Handle pasted CSV data
    if pasted:
        csv_path = save_csv(parse_pasted(pasted), uploads_dir)
        # Register pasted data in workspace
        if csv_path:
            try:
                from services.file_context_service import register_file_in_workspace
                register_file_in_workspace(session_id, csv_path, new_id(), "pasted_data.csv", {"success": True})
            except Exception:
                pass

    # Handle attached CSV — treat as activeCsv
    if attached_path and attached_type == "csv" and os.path.exists(attached_path):
        csv_path = attached_path
        # Register CSV attachment in workspace
        try:
            from services.file_context_service import register_file_in_workspace
            register_file_in_workspace(session_id, attached_path, new_id(),
                                       attached_name or "data.csv", {"success": True})
        except Exception:
            pass

    # ── WORKSPACE: Auto-resolve active dataset if no CSV provided ─────────
    # Ensures "Count districts" works in next turn after uploading a CSV.
    if not csv_path and not pasted:
        try:
            from services.file_context_service import get_active_dataset_path
            _ws_csv = get_active_dataset_path(session_id)
            if _ws_csv:
                csv_path = _ws_csv
        except Exception:
            pass

    if session_id not in chat_sessions: chat_sessions[session_id] = []
    # Store user message (with file note if attached)
    stored_user_content = user_msg
    if attached_name and attached_type and attached_type != "csv":
        stored_user_content = f"[Attached: {attached_name}]\n{user_msg}" if user_msg else f"[Attached: {attached_name}]"
    chat_sessions[session_id].append({"role":"user","content":stored_user_content})

    # ── Handle non-CSV file attached with message ──────────────────────────
    if attached_path and attached_type and attached_type not in ("csv",) and os.path.exists(attached_path):
        try:
            from services.file_router import route_file
            file_result = route_file(attached_path, new_id(), attached_name,
                                     session_id, project_id, user_msg or "")
            if file_result.get("success"):
                # Build enriched prompt from file result + user message
                file_context = ""
                if attached_type == "image":
                    file_context = file_result.get("text","")
                elif attached_type == "pdf":
                    file_context = file_result.get("preview","") or file_result.get("text","")
                elif attached_type in ("excel","docx","text"):
                    file_context = file_result.get("preview","") or ""

                # Use active provider for file analysis
                system  = "You are Atlas AI. A file has been shared with you. Answer the user's question based on the file content."
                prompt  = f"File: {attached_name}\nFile content:\n{file_context[:3000]}\n\nUser question: {user_msg}" if user_msg else f"File: {attached_name}\nFile content:\n{file_context[:3000]}\n\nDescribe what you see/read in this file."

                # Route through provider_manager so OpenAI/Anthropic work for file analysis
                try:
                    from services.providers.provider_manager import generate, get_config
                    cfg = get_config()
                    active = cfg.get("provider", "ollama")
                    if active == "openai":
                        if attached_type == "image":
                            # Use vision API for images
                            reply = _call_openai_vision(attached_path, user_msg or "Describe this image in detail.", cfg)
                        else:
                            # Use text API for all other file types (PDF, PPTX, Excel, etc.)
                            full_ctx = file_result.get("text","") or file_result.get("preview","") or ""
                            full_prompt = f"File: {attached_name}\nContent:\n{full_ctx[:6000]}\n\n{user_msg or 'Summarize and explain this file.'}"
                            reply = generate(full_prompt, system_prompt=system)
                    elif active == "anthropic":
                        full_ctx = file_result.get("text","") or file_result.get("preview","") or ""
                        full_prompt = f"File: {attached_name}\nContent:\n{full_ctx[:6000]}\n\n{user_msg or 'Summarize and explain this file.'}"
                        reply = generate(full_prompt, system_prompt=system)
                    else:
                        from utils.llm import ask_llm as _ask_llm
                        reply = _ask_llm(prompt, system_prompt=system)
                except Exception as ex:
                    from utils.llm import ask_llm as _ask_llm
                    reply = _ask_llm(prompt, system_prompt=system)

                # Auto-detect dataset
                dataset_notice = ""
                dataset_meta   = None
                if file_result.get("has_dataset"):
                    dataset_notice = file_result.get("dataset_notice","")
                    dataset_meta   = file_result.get("dataset_meta")
                    try:
                        from services.session_state import store_dataset
                        if dataset_meta: store_dataset(session_id, dataset_meta)
                    except Exception: pass

                _add(session_id,"assistant",reply)
                _flush(session_id, session_name, project_id)
                upsert_idx(session_id, session_name, project_id)
                resp = {"reply":reply,"mode":"chat","csv_path":None,"clear_csv":True,
                        "clear_attachment":True,"dataset_notice":dataset_notice,
                        "has_dataset":bool(dataset_meta)}
                if dataset_meta: resp["dataset_meta"] = dataset_meta
                return jsonify(resp)
            else:
                # File process failed — tell user clearly
                err = file_result.get("error","Unknown error processing file")
                reply = f"⚠️ Could not process {attached_name}: {err}"
                _add(session_id,"assistant",reply)
                _flush(session_id, session_name, project_id)
                return jsonify({"reply":reply,"mode":"chat","clear_attachment":True})
        except Exception as ex:
            reply = f"⚠️ File processing error: {str(ex)}"
            _add(session_id,"assistant",reply)
            _flush(session_id, session_name, project_id)
            return jsonify({"reply":reply,"mode":"chat","clear_attachment":True})

    # ── STEP 1: Check if user replies YES/NO to pending permission ────────
    try:
        from middleware.execution_guard import check_execution_guard
        from services.permission_manager import get_pending, is_confirmation, is_denial
        pending = get_pending(session_id)
        if pending and pending.get("type") == "map":
            msg_lower = user_msg.lower().strip()
            if is_confirmation(msg_lower) or is_denial(msg_lower):
                guard = check_execution_guard(user_msg, session_id, {"is_map":True}, {})
                if guard.get("denied"):
                    reply = guard["reply"]
                    _add(session_id,"assistant",reply)
                    _flush(session_id, session_name, project_id)
                    upsert_idx(session_id, session_name, project_id)
                    return jsonify({"reply":reply,"mode":"chat","csv_path":None})
                if guard.get("allowed"):
                    orig_msg  = pending.get("params",{}).get("user_msg", user_msg)
                    # Use colormap stored in pending params (for color-change requests)
                    pending_cmap = pending.get("params",{}).get("colormap")
                    colormap  = pending_cmap or sidebar_cmap or detect_color(orig_msg) or "Blues"
                    return _route_map(orig_msg, csv_path, colormap,
                                     session_id, session_name, project_id, uploads_dir)
    except Exception:
        pass

    # ── STEP 2: Detect intent ─────────────────────────────────────────────
    from services.map_context_engine import is_map_request as _is_map, references_previous_data
    from services.session_state import has_dataframe

    is_map = _is_map(user_msg) or is_map_request(user_msg, csv_path)
    refs_prev = references_previous_data(user_msg)
    has_df = has_dataframe(session_id)

    # ── STEP 2a: COLOR CHANGE — reuse session CSV with new colormap ───────
    # e.g. "create above map in red", "change colour to blue", "same map in viridis"
    if is_color_change_request(user_msg) and has_df:
        new_cmap = detect_color(user_msg) or sidebar_cmap or "Blues"
        try:
            from middleware.execution_guard import check_execution_guard
            guard = check_execution_guard(
                user_msg, session_id,
                {"is_map": True, "needs_execution": True},
                {"user_msg": user_msg, "colormap": new_cmap}
            )
            if guard.get("denied"):
                reply = guard["reply"]
                _add(session_id, "assistant", reply)
                _flush(session_id, session_name, project_id)
                upsert_idx(session_id, session_name, project_id)
                return jsonify({"reply": reply, "mode": "chat", "csv_path": None})
            if guard.get("waiting"):
                reply = guard["reply"]
                _add(session_id, "assistant", reply)
                _flush(session_id, session_name, project_id)
                upsert_idx(session_id, session_name, project_id)
                return jsonify({"reply": reply, "mode": "chat", "waiting": True, "csv_path": csv_path})
        except Exception:
            pass
        # Permission granted — regenerate map with new color from session data
        return _route_map(user_msg, csv_path, new_cmap,
                          session_id, session_name, project_id, uploads_dir)

    # ── STEP 3: If references previous data → load session dataframe ─────
    if refs_prev and has_df and not csv_path:
        try:
            from services.dataframe_manager import load_latest_dataframe
            df, meta = load_latest_dataframe(session_id)
            if df is not None and meta:
                csv_path = meta.get("csv_path")
        except Exception:
            pass

    # ── STEP 4: MAP REQUEST PIPELINE ─────────────────────────────────────
    if is_map:
        colormap = sidebar_cmap or detect_color(user_msg) or "Blues"

        # Permission gate
        try:
            from middleware.execution_guard import check_execution_guard
            guard = check_execution_guard(
                user_msg, session_id,
                {"is_map":True, "needs_execution":True},
                {"user_msg": user_msg}
            )
            if guard.get("denied"):
                reply = guard["reply"]
                _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
                upsert_idx(session_id, session_name, project_id)
                return jsonify({"reply":reply,"mode":"chat","csv_path":None,"clear_csv":True})
            if guard.get("waiting"):
                reply = guard["reply"]
                _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
                upsert_idx(session_id, session_name, project_id)
                return jsonify({"reply":reply,"mode":"chat","waiting":True,"csv_path":csv_path})
        except Exception:
            pass

        return _route_map(user_msg, csv_path, colormap,
                         session_id, session_name, project_id, uploads_dir)

    # ── STEP 5: NORMAL CHAT with full context + RAG ──────────────────────
    # Intent classification
    try:
        from services.intent_router import route as classify_intent
        from services.session_state import has_dataframe as _has_df
        intent_info = classify_intent(
            user_msg,
            has_file=bool(csv_path),
            has_session_df=_has_df(session_id),
        )
    except Exception:
        intent_info = {"intent": "normal_chat", "refs_previous": False}

    # ── WORKSPACE: Context injection + tool-first data execution ──────────
    workspace_context  = ""
    tool_result_prefix = ""
    try:
        from services.file_context_service import build_workspace_context, get_active_dataset_path
        from services.workspace_manager import get_workspace, log_analysis
        from services.command_router import classify as _classify_cmd, build_tool_result_prefix as _build_prefix
        from services.dataset_manager import execute_data_query

        workspace_context = build_workspace_context(session_id, user_msg)
        ws = get_workspace(session_id)

        # Attempt tool-first execution if dataset exists in workspace or csv_path set
        if ws.get("registered_files") or csv_path:
            cmd = _classify_cmd(user_msg, ws)
            if cmd["op_type"] == "DATA_OPERATION":
                ds_path = csv_path or get_active_dataset_path(session_id)
                if ds_path and os.path.exists(ds_path):
                    active_ds_id = ws.get("active_dataset")
                    active_ds    = ws.get("registered_files", {}).get(active_ds_id, {})
                    profile      = active_ds.get("profile", {})
                    # Fallback: build profile stub from session_state
                    if not profile:
                        try:
                            from services.session_state import get_latest_dataset
                            ss_ds   = get_latest_dataset(session_id) or {}
                            profile = {
                                "geo_col":   ss_ds.get("geo_col"),
                                "value_col": ss_ds.get("value_col"),
                                "columns":   ss_ds.get("columns", []),
                            }
                        except Exception:
                            pass
                    exec_result = execute_data_query(user_msg, ds_path, profile)
                    if exec_result.get("executed"):
                        tool_result_prefix = _build_prefix("DATA_OPERATION", exec_result)
                        log_analysis(session_id, user_msg, exec_result.get("result_text", ""))
    except Exception:
        pass

    # Semantic retrieval context
    rag_context = ""
    try:
        from services.vector_memory import retrieve_as_context
        rag_context = retrieve_as_context(user_msg, namespace=session_id, top_k=3)
        if project_id:
            proj_ctx = retrieve_as_context(user_msg, namespace=project_id, top_k=2)
            if proj_ctx: rag_context = (rag_context + "\n\n" + proj_ctx).strip()
    except Exception:
        pass

    # Merge RAG + workspace context into extra_system
    extra_system = rag_context
    if workspace_context:
        extra_system = (extra_system + "\n\n" + workspace_context).strip() if extra_system else workspace_context

    try:
        from services.context_manager import build_prompt
        system, full_msg = build_prompt(user_msg, session_id, project_id,
                                        extra_system=extra_system)
    except Exception:
        system   = "You are Atlas AI, a smart geographic intelligence assistant."
        full_msg = (extra_system + "\n\n" + user_msg) if extra_system else user_msg

    # Tool-first: prepend backend-computed result → LLM explains exact answer
    if tool_result_prefix:
        full_msg = tool_result_prefix + full_msg

    # ── Tool-calling LLM dispatch ─────────────────────────────────────────
    # LLM decides: text reply OR call generate_choropleth_map / query_dataset
    reply = None

    # ── Keyword fallback graph detection (Ollama has no tool calling) ─────
    _graph_tool_kw = None
    try:
        from services.graph_dispatcher import detect_graph_intent
        _graph_tool_kw = detect_graph_intent(user_msg)
    except Exception:
        pass

    if _graph_tool_kw:
        try:
            df_kw = None
            from utils.data_parser import parse_message_data, parse_uploaded_file
            df_kw = parse_message_data(user_msg)
            if df_kw is None and csv_path and os.path.exists(csv_path):
                df_kw, _kw_err = parse_uploaded_file(csv_path)
            if df_kw is None and attached_path and os.path.exists(attached_path):
                df_kw, _kw_err = parse_uploaded_file(attached_path)
            if df_kw is not None and not df_kw.empty:
                from services.graph_dispatcher import dispatch as _gd
                g_result = _gd(_graph_tool_kw, df_kw, {"title": clean_title(user_msg)})
                if g_result["status"] == "ok":
                    reply = f"\U0001f4ca {g_result['description']}\n\n![]({g_result['image_url']})"
                    _add(session_id, "assistant", reply)
                    _flush(session_id, session_name, project_id)
                    upsert_idx(session_id, session_name, project_id)
                    return jsonify({"reply": reply, "mode": "graph",
                                    "image_url": g_result["image_url"], "csv_path": csv_path})
                else:
                    reply = f"\u26a0\ufe0f Graph error: {g_result['message']}"
            else:
                chart_name = _graph_tool_kw.replace("generate_", "").replace("_", " ")
                reply = (f"\U0001f4ce Please paste your data in the message or attach a "
                         f"CSV/Excel file to generate a {chart_name}.")
        except Exception as _ge:
            reply = f"\u26a0\ufe0f Graph generation failed: {_ge}"

    if reply is None:
        try:
            from services.providers.provider_manager import generate_with_tools
            tool_result = generate_with_tools(full_msg, system_prompt=system)

            if tool_result["type"] == "tool_use":
                tool_name  = tool_result["tool_name"]
                tool_input = tool_result["tool_input"]

                from services.graph_dispatcher import all_tool_names as _gtn, dispatch as _gd2
                if tool_name in _gtn():
                    try:
                        df_tc = None
                        from utils.data_parser import parse_message_data, parse_uploaded_file
                        df_tc = parse_message_data(user_msg)
                        if df_tc is None and csv_path and os.path.exists(csv_path):
                            df_tc, _ = parse_uploaded_file(csv_path)
                        if df_tc is None and attached_path and os.path.exists(attached_path):
                            df_tc, _ = parse_uploaded_file(attached_path)
                        if df_tc is not None and not df_tc.empty:
                            g_cfg = {"title": tool_input.get("title") or clean_title(user_msg)}
                            g_result = _gd2(tool_name, df_tc, g_cfg)
                            if g_result["status"] == "ok":
                                reply = f"\U0001f4ca {g_result['description']}\n\n![]({g_result['image_url']})"
                                _add(session_id, "assistant", reply)
                                _flush(session_id, session_name, project_id)
                                upsert_idx(session_id, session_name, project_id)
                                return jsonify({"reply": reply, "mode": "graph",
                                                "image_url": g_result["image_url"], "csv_path": csv_path})
                            else:
                                reply = f"\u26a0\ufe0f Graph error: {g_result['message']}"
                        else:
                            reply = "\U0001f4ce Please paste data or attach a CSV/Excel file to generate this chart."
                    except Exception as _ge2:
                        reply = f"\u26a0\ufe0f Graph generation failed: {_ge2}"

                elif tool_name == "generate_choropleth_map":
                    colormap = sidebar_cmap or detect_color(user_msg) or "Blues"
                    try:
                        from middleware.execution_guard import check_execution_guard
                        guard = check_execution_guard(
                            user_msg, session_id,
                            {"is_map": True, "needs_execution": True},
                            {"user_msg": user_msg}
                        )
                        if guard.get("denied"):
                            reply = guard["reply"]
                            _add(session_id, "assistant", reply)
                            _flush(session_id, session_name, project_id)
                            upsert_idx(session_id, session_name, project_id)
                            return jsonify({"reply": reply, "mode": "chat", "csv_path": None})
                        if guard.get("waiting"):
                            reply = guard["reply"]
                            _add(session_id, "assistant", reply)
                            _flush(session_id, session_name, project_id)
                            upsert_idx(session_id, session_name, project_id)
                            return jsonify({"reply": reply, "mode": "chat",
                                            "waiting": True, "csv_path": csv_path})
                    except Exception:
                        pass
                    return _route_map(
                        tool_input.get("intent", user_msg), csv_path, colormap,
                        session_id, session_name, project_id, uploads_dir
                    )

                elif tool_name == "query_dataset":
                    reply = ask_llm((tool_result_prefix or "") + full_msg, system_prompt=system)

                else:
                    reply = tool_result.get("content") or ask_llm(full_msg, system_prompt=system)

            else:
                reply = tool_result.get("content") or ask_llm(full_msg, system_prompt=system)

        except Exception:
            reply = ask_llm(full_msg, system_prompt=system)
            try:
                from services.providers.provider_manager import generate, get_config
                if get_config().get("provider", "ollama") != "ollama":
                    reply = generate(full_msg, system_prompt=system)
            except Exception:
                pass

    # ── STEP 6: Parse response — auto-detect structured data ─────────────
    dataset_notice = ""
    dataset_meta   = None
    try:
        from services.response_parser import parse_response
        parsed = parse_response(reply, session_id, user_msg)
        if parsed["has_dataset"]:
            dataset_notice = parsed["dataset_notice"]
            dataset_meta   = parsed["dataset_meta"]
    except Exception:
        pass

    _add(session_id,"assistant",reply)

    # Store both turns in vector memory for future RAG
    try:
        from services.vector_memory import store_conversation_turn
        store_conversation_turn(session_id, "user",      user_msg)
        store_conversation_turn(session_id, "assistant", reply)
        if project_id:
            store_conversation_turn(project_id, "user",      user_msg)
            store_conversation_turn(project_id, "assistant", reply)
    except Exception:
        pass

    _flush(session_id, session_name, project_id)
    upsert_idx(session_id, session_name, project_id)

    response_payload = {
        "reply":          reply,
        "mode":           "chat",
        "csv_path":       csv_path,
        "dataset_notice": dataset_notice,
        "has_dataset":    bool(dataset_meta),
    }
    if dataset_meta:
        response_payload["dataset_meta"] = {
            "rows":      dataset_meta.get("rows",0),
            "columns":   dataset_meta.get("columns",[]),
            "geo_scope": dataset_meta.get("geo_scope",""),
            "label":     dataset_meta.get("label",""),
        }
    return jsonify(response_payload)


def _route_map(user_msg, csv_path, colormap, session_id, session_name, project_id, uploads_dir):
    """
    Route map generation through priority order:
    1. Uploaded CSV (explicit) — always use
    2. Session dataframe — ONLY if topic matches current request
    3. Baseline dataset factory (known topics)
    4. LLM data extraction (unknown topics)
    """
    # Priority 1: Explicit uploaded CSV
    if csv_path and os.path.exists(csv_path):
        return _pipeline_from_csv(csv_path, user_msg, colormap,
                                   session_id, session_name, project_id)

    # Priority 2: Session dataframe — topic-validated to prevent hallucination
    # Only reuse if user explicitly references previous data OR topic matches
    try:
        from services.map_context_engine import get_map_params_from_session, references_previous_data
        from services.session_state import get_session_state
        refs_prev = references_previous_data(user_msg)

        if refs_prev:
            # User explicitly said "above data", "previous CSV" etc. — safe to reuse
            params = get_map_params_from_session(session_id, user_msg, colormap)
            if params:
                return _pipeline_from_csv(
                    params["csv_path"], user_msg, colormap,
                    session_id, session_name, project_id,
                    title_override=params["title"],
                    district_col=params["district_col"],
                    value_col=params["value_col"],
                )
        # If NOT referencing previous data, skip session dataframe entirely
        # This prevents: "generate GDP map" using old population CSV
    except Exception:
        pass

    # Priority 3: baseline dataset factory
    from services.dataset_factory import generate_dataset, DATA_NOT_AVAILABLE
    dataset = generate_dataset(user_msg)
    if dataset.get("status") == "ok":
        return _pipeline_from_dataset(dataset, user_msg, colormap,
                                       session_id, session_name, project_id)

    # Priority 4: LLM data extraction
    topic, geography, metric_col = infer_topic_geography_metric(user_msg)
    extraction = extract_data_from_llm(topic, geography, metric_col)
    if extraction["status"] == "no_data":
        reply = extraction["reason"]
        _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
        upsert_idx(session_id, session_name, project_id)
        return jsonify({"reply":reply,"mode":"chat","csv_path":None})

    fresh_csv = _save_extracted_csv(extraction["csv_text"], uploads_dir)
    if not fresh_csv:
        reply = "⚠️ Failed to save extracted data. Please upload a CSV manually."
        _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
        return jsonify({"reply":reply,"mode":"chat"})

    title = f"{geography} District {topic.title()} Distribution"
    return _pipeline_from_csv(
        fresh_csv, user_msg, colormap,
        session_id, session_name, project_id,
        title_override=title,
        district_col=extraction.get("district_col"),
        value_col=extraction.get("value_col"),
    )


def _save_extracted_csv(csv_text, uploads_dir):
    try:
        os.makedirs(uploads_dir, exist_ok=True)
        fpath = os.path.join(uploads_dir, f"llm_{new_id()}.csv")
        with open(fpath,"w",newline="",encoding="utf-8") as f: f.write(csv_text)
        return fpath
    except Exception: return None


def _pipeline_from_dataset(dataset, user_msg, colormap, session_id, session_name, project_id):
    region       = dataset.get("region","Karnataka")
    metric_label = dataset.get("dataset_label","").replace(f"{region} District ","")
    title        = f"{region} District {metric_label} Distribution".strip()
    return _run_map_pipeline(
        source_csv=None, dataset=dataset, user_msg=user_msg, colormap=colormap,
        title=title, subtitle=f"{len(dataset.get('rows',[]))} district records",
        legend_title=metric_label, value_col=dataset.get("value_col","value"),
        district_col=dataset.get("district_col","district"),
        session_id=session_id, session_name=session_name, project_id=project_id,
    )


def _pipeline_from_csv(csv_path, user_msg, colormap, session_id, session_name, project_id,
                        title_override=None, district_col=None, value_col=None):
    from utils.map_generator import detect_columns
    from services.geo_matcher import normalize_dataframe_districts
    import pandas as pd

    if not district_col or not value_col:
        dc, vc, cols = detect_columns(csv_path)

        # ── CHOROPLETH AUTONOMY: auto-aggregate if no value column ────────
        # E.g. raw students.xlsx with just District column → count by district
        if dc and not vc:
            try:
                df_raw = pd.read_csv(csv_path) if csv_path.endswith(".csv") else pd.read_excel(csv_path)
                # Normalize district names before aggregating
                try:
                    from services.geography_normalizer import normalize_series
                    df_raw[dc] = normalize_series(df_raw[dc])
                except Exception:
                    pass
                df_agg = df_raw.groupby(dc).size().reset_index(name="Count")
                import os, tempfile
                agg_path = os.path.join(os.path.dirname(csv_path), f"agg_{dc.lower()[:8]}_{os.urandom(4).hex()}.csv")
                df_agg.to_csv(agg_path, index=False)
                csv_path  = agg_path
                vc        = "Count"
                district_col, value_col = dc, vc
            except Exception:
                pass

        if not district_col or not value_col:
            if not dc or not vc:
                reply = f"⚠️ CSV needs at least 2 columns. Found: {cols}"
                _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
                return jsonify({"reply":reply,"mode":"chat","csv_path":None,"clear_csv":True})
            district_col, value_col = dc, vc

    # Apply fuzzy district normalization + geography_normalizer
    try:
        df = pd.read_csv(csv_path)
        # geography_normalizer (new, more complete)
        try:
            from services.geography_normalizer import normalize_series
            df[district_col] = normalize_series(df[district_col])
        except Exception:
            pass
        # existing geo_matcher as second pass
        df = normalize_dataframe_districts(df, district_col)
        df.to_csv(csv_path, index=False)
    except Exception: pass

    if title_override:
        title = title_override
    else:
        try:
            from services.metadata_generator import generate_smart_title
            meta  = generate_smart_title(csv_path, user_msg, district_col, value_col)
            title = meta.get("title", clean_title(user_msg) or f"{value_col} by {district_col}")
        except Exception:
            title = clean_title(user_msg) or f"{value_col} by {district_col}"

    dataset = {"district_col":district_col,"value_col":value_col,"source":"uploaded_csv","rows":[]}
    return _run_map_pipeline(
        source_csv=csv_path, dataset=dataset, user_msg=user_msg, colormap=colormap,
        title=title, subtitle="", legend_title=value_col, value_col=value_col,
        district_col=district_col, session_id=session_id,
        session_name=session_name, project_id=project_id,
    )


def _run_map_pipeline(source_csv, dataset, user_msg, colormap, title, subtitle,
                       legend_title, value_col, district_col, session_id, session_name, project_id):
    from utils.map_generator import generate_map_code, run_map_code
    from utils.execution_state import create_map_request, update_state, finalize_map_state, cleanup_request
    from services.session_state import store_map

    metadata = {
        "title":           title,
        "subtitle":        subtitle or "",
        "legend_title":    legend_title or value_col,
        "dataset_label":   f"{district_col} {value_col}",
        "export_filename": title.lower().replace(" ","_")[:50] + ".png",
    }
    state    = create_map_request(session_id, user_msg, dataset, metadata, colormap, source_csv or "")
    maps_dir = os.path.join(STORAGE,"maps")
    os.makedirs(maps_dir, exist_ok=True)
    update_state(state["request_id"], status="executing")

    code    = generate_map_code(
        state["temporary_csv"], district_col, value_col,
        state["temporary_output"], title, colormap,
        subtitle=subtitle or "", legend_title=legend_title or value_col,
    )
    success, result = run_map_code(code, maps_dir)

    if success:
        map_id    = new_id()
        finalized = finalize_map_state(state, map_id)
        store_map(session_id, map_id, title, colormap)

        hf   = os.path.join(STORAGE,"history","index.json")
        hist = read_json(hf,[])
        hist.insert(0,{
            "id":map_id,"title":title,"colormap":colormap,
            "district_col":district_col,"value_col":value_col,
            "session_id":session_id,"project_id":project_id,
            "timestamp":now(),"map_file":finalized["map_file"],
            "csv_file":finalized["csv_file"],"metadata_file":finalized["json_file"],
        })
        write_json(hf, hist[:100])

        # IMPORTANT: store map URL in message content with __MAP__ prefix
        # This allows loadChat() to re-render the map when chat is revisited
        map_url = finalized["map_url"]
        map_msg = f"__MAP__{map_id}::{map_url}"
        _add(session_id,"assistant", map_msg)
        _flush(session_id, session_name, project_id)
        upsert_idx(session_id, session_name, project_id)
        cleanup_request(state["request_id"])
        return jsonify({"reply":"","mode":"map","map_url":map_url,
                        "map_id":map_id,"csv_path":None,"clear_csv":True})

    cleanup_request(state["request_id"])
    reply = f"⚠️ Map generation failed.\n\nError:\n```\n{result[:600]}\n```"
    _add(session_id,"assistant",reply); _flush(session_id, session_name, project_id)
    return jsonify({"reply":reply,"mode":"map","error":result,"csv_path":None,"clear_csv":True})


def _add(sid, role, content):
    if sid not in chat_sessions: chat_sessions[sid] = []
    msgs = chat_sessions[sid]
    if not msgs or msgs[-1]["content"] != content:
        msgs.append({"role":role,"content":content})

def _flush(sid, name, project_id=None):
    write_json(chat_file(sid),{"id":sid,"name":name,"project_id":project_id,
                               "timestamp":now(),"messages":chat_sessions.get(sid,[])})


@chat_bp.route("/list",         methods=["GET"])
def list_chats(): return jsonify(load_idx()[:40])

@chat_bp.route("/recent",       methods=["GET"])
def recent_chats():
    return jsonify([c for c in load_idx() if not c.get("project_id")][:30])

@chat_bp.route("/get/<sid>",    methods=["GET"])
def get_chat(sid): return jsonify(read_json(chat_file(sid),{"messages":[]}))

@chat_bp.route("/search",       methods=["GET"])
def search_chats():
    q = request.args.get("q","").lower()
    results = []
    for c in load_idx():
        if q in c.get("name","").lower(): results.append(c); continue
        d = read_json(chat_file(c["id"]),{})
        if q in " ".join(m.get("content","") for m in d.get("messages",[])).lower():
            results.append(c)
    return jsonify(results[:20])

@chat_bp.route("/delete/<sid>", methods=["DELETE","OPTIONS"])
def delete_chat(sid):
    if request.method == "OPTIONS": return jsonify({}), 200
    save_idx([c for c in load_idx() if c["id"]!=sid])
    cf = chat_file(sid)
    if os.path.exists(cf): os.remove(cf)
    if sid in chat_sessions: del chat_sessions[sid]
    try:
        from services.session_state import clear_session
        clear_session(sid)
    except Exception: pass
    try:
        from services.workspace_manager import clear_workspace
        clear_workspace(sid)
    except Exception: pass
    return jsonify({"ok":True})

@chat_bp.route("/session-state/<sid>", methods=["GET"])
def session_state(sid):
    """Frontend polls this to show active dataframe badge."""
    try:
        from services.session_state import get_session_state
        state = get_session_state(sid)
        ds    = state.get("latest_dataset",{})
        return jsonify({
            "has_dataframe":  state.get("has_dataframe", False),
            "dataset_label":  ds.get("label",""),
            "dataset_rows":   ds.get("rows",0),
            "dataset_columns":ds.get("columns",[]),
            "geo_scope":      ds.get("geo_scope",""),
        })
    except Exception:
        return jsonify({"has_dataframe":False})
