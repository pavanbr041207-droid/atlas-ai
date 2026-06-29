"""
services/providers/provider_manager.py
Routes all LLM calls to the active provider.
Reads config from backend/config/providers.json.
Supports: Ollama, OpenAI, Anthropic.
Map generation code is NOT affected — it calls utils/llm.py directly.
"""
import os, json, requests

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "providers.json")
KEYS_PATH   = os.path.join(BASE_DIR, "config", "api_keys.json")


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"provider": "ollama", "ollama_model": "qwen2.5:7b",
                "temperature": 0.3, "max_tokens": 2048}


def _save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _load_keys() -> dict:
    try:
        with open(KEYS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_keys(keys: dict):
    os.makedirs(os.path.dirname(KEYS_PATH), exist_ok=True)
    with open(KEYS_PATH, "w") as f:
        json.dump(keys, f, indent=2)


def get_config() -> dict:
    return _load_config()


def update_config(updates: dict) -> dict:
    cfg = _load_config()
    cfg.update(updates)
    _save_config(cfg)
    # Also sync Ollama model to utils/llm.py at runtime
    if "ollama_model" in updates and cfg.get("provider") == "ollama":
        _sync_llm_model(updates["ollama_model"])
    return cfg


def set_api_key(provider: str, key: str):
    keys = _load_keys()
    keys[provider] = key
    _save_keys(keys)


def get_api_key(provider: str) -> str:
    return _load_keys().get(provider, "")


def _sync_llm_model(model_name: str):
    """Update MODEL_NAME in utils/llm.py at runtime."""
    try:
        import utils.llm as llm_module
        llm_module.MODEL_NAME = model_name
    except Exception:
        pass


def generate(prompt: str, system_prompt: str = None) -> str:
    """
    Route to active provider. Returns response text.
    Used by chat — NOT by map generation (which uses utils.llm directly).
    """
    cfg      = _load_config()
    provider = cfg.get("provider", "ollama")

    if provider == "openai":
        return _call_openai(prompt, system_prompt, cfg)
    elif provider == "anthropic":
        return _call_anthropic(prompt, system_prompt, cfg)
    else:
        return _call_ollama(prompt, system_prompt, cfg)


def _call_ollama(prompt: str, system_prompt: str, cfg: dict) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    try:
        r = requests.post(
            f"{cfg.get('ollama_url','http://localhost:11434')}/api/chat",
            json={
                "model":   cfg.get("ollama_model", "qwen2.5:7b"),
                "messages":messages,
                "stream":  False,
                "options": {
                    "temperature": cfg.get("temperature", 0.3),
                    "num_predict": cfg.get("max_tokens", 2048),
                }
            }, timeout=180
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        return "❌ Cannot connect to Ollama. Run `ollama serve` in terminal."
    except Exception as e:
        return f"❌ Ollama error: {e}"


def _call_openai(prompt: str, system_prompt: str, cfg: dict) -> str:
    key = get_api_key("openai").strip()
    if not key:
        return "❌ OpenAI API key not set. Go to Settings → API Keys to add it."
    try:
        import openai
        client = openai.OpenAI(api_key=key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=cfg.get("openai_model", "gpt-4o"),
            messages=messages,
            max_tokens=cfg.get("max_tokens", 2048),
            temperature=cfg.get("temperature", 0.3),
        )
        return resp.choices[0].message.content
    except ImportError:
        return "❌ openai package not installed. Run: pip install openai --break-system-packages"
    except openai.AuthenticationError:
        return "❌ OpenAI key rejected. Check key is correct and has billing enabled at platform.openai.com/billing"
    except openai.RateLimitError:
        return "❌ OpenAI rate limit or quota exceeded. Check usage at platform.openai.com/usage"
    except Exception as e:
        return f"❌ OpenAI error: {e}"


def _call_anthropic(prompt: str, system_prompt: str, cfg: dict) -> str:
    key = get_api_key("anthropic")
    if not key:
        return "❌ Anthropic API key not set. Go to Settings → API Keys to add it."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=cfg.get("anthropic_model", "claude-sonnet-4-6"),
            max_tokens=cfg.get("max_tokens", 2048),
            system=system_prompt or "You are Atlas AI.",
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except ImportError:
        return "❌ anthropic package not installed. Run: pip install anthropic --break-system-packages"
    except Exception as e:
        return f"❌ Anthropic error: {e}"


def generate_with_tools(prompt: str, system_prompt: str = None) -> dict:
    """
    Call active provider with tool schemas. Returns:
      {"type": "text",     "content": "..."}
      {"type": "tool_use", "tool_name": "...", "tool_input": {...}}
    Ollama: skips tool schemas, uses plain ask_llm().
    """
    cfg      = _load_config()
    provider = cfg.get("provider", "ollama")
    try:
        if provider == "openai":
            return _call_openai_with_tools(prompt, system_prompt, cfg)
        elif provider == "anthropic":
            return _call_anthropic_with_tools(prompt, system_prompt, cfg)
        else:
            from utils.llm import ask_llm
            content = ask_llm(prompt, system_prompt=system_prompt)
            return {"type": "text", "content": content}
    except Exception as e:
        return {"type": "text", "content": f"Tool call error: {e}"}


def _call_anthropic_with_tools(prompt: str, system_prompt: str, cfg: dict) -> dict:
    from services.tool_definitions import ATLAS_TOOLS_ANTHROPIC
    key = get_api_key("anthropic")
    if not key:
        return {"type": "text", "content": "❌ Anthropic API key not set."}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=cfg.get("anthropic_model", "claude-sonnet-4-6"),
            max_tokens=cfg.get("max_tokens", 2048),
            system=system_prompt or "You are Atlas AI.",
            messages=[{"role": "user", "content": prompt}],
            tools=ATLAS_TOOLS_ANTHROPIC,
        )
        for block in resp.content:
            if block.type == "tool_use":
                return {"type": "tool_use", "tool_name": block.name, "tool_input": block.input}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return {"type": "text", "content": text}
    except Exception as e:
        return {"type": "text", "content": f"❌ Anthropic tool call error: {e}"}


def _call_openai_with_tools(prompt: str, system_prompt: str, cfg: dict) -> dict:
    from services.tool_definitions import ATLAS_TOOLS_OPENAI
    key = get_api_key("openai").strip()
    if not key:
        return {"type": "text", "content": "❌ OpenAI API key not set."}
    try:
        import openai, json as _json
        client = openai.OpenAI(api_key=key)
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=cfg.get("openai_model", "gpt-4o"),
            messages=msgs,
            tools=ATLAS_TOOLS_OPENAI,
            tool_choice="auto",
            max_tokens=cfg.get("max_tokens", 2048),
            temperature=cfg.get("temperature", 0.3),
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            return {
                "type":       "tool_use",
                "tool_name":  tc.function.name,
                "tool_input": _json.loads(tc.function.arguments),
            }
        return {"type": "text", "content": msg.content or ""}
    except Exception as e:
        return {"type": "text", "content": f"❌ OpenAI tool call error: {e}"}


def _call_ollama_with_tools(prompt: str, system_prompt: str, cfg: dict) -> dict:
    from services.tool_definitions import ATLAS_TOOLS_OLLAMA
    base_url = cfg.get("ollama_url", "http://localhost:11434")
    model    = cfg.get("ollama_model", "qwen2.5:7b")
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": prompt})
    try:
        r = requests.post(
            f"{base_url}/api/chat",
            json={
                "model":    model,
                "messages": msgs,
                "tools":    ATLAS_TOOLS_OLLAMA,
                "stream":   False,
                "options": {
                    "temperature": cfg.get("temperature", 0.3),
                    "num_predict": cfg.get("max_tokens", 2048),
                },
            }, timeout=180
        )
        # Ollama < 0.3.0 returns 404 for tool calls — fall back to plain chat
        if r.status_code == 404:
            return _call_ollama_plain(prompt, system_prompt, cfg, base_url, model, msgs)
        r.raise_for_status()
        resp_msg   = r.json().get("message", {})
        tool_calls = resp_msg.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            fn = tc.get("function", {})
            return {
                "type":       "tool_use",
                "tool_name":  fn.get("name", ""),
                "tool_input": fn.get("arguments", {}),
            }
        return {"type": "text", "content": resp_msg.get("content", "")}
    except requests.exceptions.ConnectionError:
        return {"type": "text", "content": "❌ Cannot connect to Ollama. Run `ollama serve` in terminal."}
    except Exception as e:
        return {"type": "text", "content": f"❌ Ollama tool call error: {e}"}


def _call_ollama_plain(prompt: str, system_prompt: str, cfg: dict,
                       base_url: str, model: str, msgs: list) -> dict:
    """Fallback plain Ollama chat — used when server doesn't support tool calling."""
    try:
        r = requests.post(
            f"{base_url}/api/chat",
            json={
                "model":    model,
                "messages": msgs,
                "stream":   False,
                "options": {
                    "temperature": cfg.get("temperature", 0.3),
                    "num_predict": cfg.get("max_tokens", 2048),
                },
            }, timeout=180
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")
        return {"type": "text", "content": content}
    except Exception as e:
        return {"type": "text", "content": f"❌ Ollama error: {e}"}


def list_ollama_models() -> list:
    cfg = _load_config()
    try:
        r = requests.get(
            f"{cfg.get('ollama_url','http://localhost:11434')}/api/tags",
            timeout=5
        )
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def get_provider_status() -> dict:
    cfg  = _load_config()
    keys = _load_keys()

    # Ollama status
    ollama_ok = False
    try:
        r = requests.get(
            f"{cfg.get('ollama_url','http://localhost:11434')}/api/tags",
            timeout=3
        )
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    # OpenAI status — check key format only, no API call needed
    openai_ok = False
    if keys.get("openai"):
        k = keys["openai"].strip()
        openai_ok = k.startswith("sk-") and len(k) > 30

    # Anthropic status
    anthropic_ok = False
    if keys.get("anthropic"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=keys["anthropic"])
            client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1,
                messages=[{"role":"user","content":"hi"}]
            )
            anthropic_ok = True
        except Exception:
            pass

    return {
        "ollama":    "running" if ollama_ok else "stopped",
        "openai":    "connected" if openai_ok else ("invalid_key" if keys.get("openai") else "no_key"),
        "anthropic": "connected" if anthropic_ok else ("invalid_key" if keys.get("anthropic") else "no_key"),
        "active_provider": cfg.get("provider","ollama"),
        "active_model":    cfg.get("ollama_model","qwen2.5:7b"),
    }
