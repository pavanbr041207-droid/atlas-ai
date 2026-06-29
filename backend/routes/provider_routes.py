"""
routes/provider_routes.py
Settings API: model list, config CRUD, API keys, provider status.
Map generation routes are untouched.
"""
from flask import Blueprint, request, jsonify

provider_bp = Blueprint("providers", __name__)


@provider_bp.route("/ollama", methods=["GET"])
def ollama_models():
    from services.providers.provider_manager import list_ollama_models
    return jsonify(list_ollama_models())


@provider_bp.route("/config", methods=["GET"])
def get_config():
    from services.providers.provider_manager import get_config, get_api_key
    cfg = get_config()
    # Never expose actual keys — just whether they are set
    cfg["openai_key_set"]    = bool(get_api_key("openai"))
    cfg["anthropic_key_set"] = bool(get_api_key("anthropic"))
    return jsonify(cfg)


@provider_bp.route("/config", methods=["POST", "OPTIONS"])
def update_config():
    if request.method == "OPTIONS": return jsonify({}), 200
    from services.providers.provider_manager import update_config
    data = request.json or {}
    # Don't allow updating keys through this endpoint
    data.pop("openai_key", None)
    data.pop("anthropic_key", None)
    cfg = update_config(data)
    return jsonify({"ok": True, "config": cfg})


@provider_bp.route("/keys", methods=["POST", "OPTIONS"])
def set_keys():
    if request.method == "OPTIONS": return jsonify({}), 200
    from services.providers.provider_manager import set_api_key
    data = request.json or {}
    for provider in ("openai", "anthropic"):
        if provider in data and data[provider]:
            set_api_key(provider, data[provider])
    return jsonify({"ok": True})


@provider_bp.route("/status", methods=["GET"])
def provider_status():
    from services.providers.provider_manager import get_provider_status
    return jsonify(get_provider_status())


@provider_bp.route("/anthropic-models", methods=["POST","OPTIONS"])
def anthropic_models():
    if request.method == "OPTIONS": return jsonify({}), 200
    data = request.json or {}
    key  = data.get("key","").strip()
    if not key:
        return jsonify({"models":[],"error":"No key provided"}), 400
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        # Anthropic SDK model list
        models_raw = client.models.list()
        models = [{"id": m.id, "name": m.display_name if hasattr(m,"display_name") else m.id}
                  for m in models_raw.data]
        return jsonify({"models": models})
    except ImportError:
        # Fallback: return well-known models
        return jsonify({"models":[
            {"id":"claude-opus-4-6",    "name":"Claude Opus 4.6"},
            {"id":"claude-sonnet-4-6",  "name":"Claude Sonnet 4.6"},
            {"id":"claude-haiku-4-5",   "name":"Claude Haiku 4.5"},
            {"id":"claude-opus-4-8",    "name":"Claude Opus 4.8"},
        ]})
    except Exception as e:
        return jsonify({"models":[],"error":str(e)}), 400
