/**
 * script.js — Atlas AI LMS
 * Full ChatGPT-like: chat, projects, maps, notes, study tools
 */

const BACKEND = "http://127.0.0.1:5001";

// ── State ──
let sessionId    = 'sess_' + Date.now();
let sessionName  = 'New Chat';
let selectedCmap = "Blues";
let activeCsv    = null;
let isWaiting    = false;           // global flag for current session
const _sessionLocks = new Map();    // per-session lock: sessionId -> AbortController
let hasMessages  = false;
let mapSBOpen    = false;
let sbOpen       = true;
let editingEl    = null;
let currentMapId = null;
let currentTitle = "";
let currentProjId= null;   // selected project in projects view
let moveChatId   = null;   // chat being moved
let moveProjSel  = null;   // selected target project
let projIcon     = "📁";
let timerSecs    = 25*60;
let timerRun     = false;
let timerIv      = null;

// Attachment state — file waits until user clicks Send, then goes WITH the message
let activeAttachment = null; // { path, type, name, ext, icon }
let activeNoteId = null;
let activeProjectId = null; // project context for current chat

// ─────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  checkConn();
  loadChatList();
  loadSBProjects();
  document.getElementById("msgInput").focus();
});

// ─────────────────────────────────────────────────────────
// CONNECTION
// ─────────────────────────────────────────────────────────
async function checkConn() {
  const dot = document.getElementById("connDot");
  const lbl = document.getElementById("connLbl");
  try {
    const r = await fetch(`${BACKEND}/api/health`, { signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      dot.className  = "conn-dot ok";
      lbl.textContent = "connected";
    } else { throw new Error(); }
  } catch {
    dot.className  = "conn-dot err";
    lbl.textContent = "offline — run app.py";
  }
}

// ─────────────────────────────────────────────────────────
// SIDEBAR
// ─────────────────────────────────────────────────────────
function toggleSB() {
  sbOpen = !sbOpen;
  document.getElementById("sidebar").classList.toggle("collapsed", !sbOpen);
}

// ─────────────────────────────────────────────────────────
// VIEW SWITCHING
// ─────────────────────────────────────────────────────────
function switchView(name, btn) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById("view-" + name).classList.add("active");
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  if (name === "maps")     { switchMapsTab("history"); }
  if (name === "projects") { loadProjectsList(); }
  if (name === "notes")    loadNotesView();
}

function toggleTheme() {
  const t = document.documentElement.getAttribute("data-theme");
  document.documentElement.setAttribute("data-theme", t === "light" ? "" : "light");
}

// ─────────────────────────────────────────────────────────
// MAP SIDEBAR
// ─────────────────────────────────────────────────────────
function toggleMSB() {
  mapSBOpen = !mapSBOpen;
  document.getElementById("mapSidebar").classList.toggle("open", mapSBOpen);
}
function showMSB() {
  mapSBOpen = true;
  document.getElementById("mapSidebar").classList.add("open");
  document.getElementById("mapTogBtn").style.display = "flex";
}
function msbTab(name, btn) {
  document.querySelectorAll(".msb-tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll(".msb-pane").forEach(p => p.classList.remove("active"));
  document.getElementById("msb-" + name).classList.add("active");
  if (name === "history") loadMapHistory();
}

// ─────────────────────────────────────────────────────────
// COLOR
// ─────────────────────────────────────────────────────────
function pickColor(el) {
  document.querySelectorAll(".cmap").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
  selectedCmap = el.dataset.cmap;
  toast("Color: " + selectedCmap);
}

// ─────────────────────────────────────────────────────────
// CHIP FILL
// ─────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════
// CHAT CONCURRENCY CONTROL — ChatGPT-style locking
// Only current session locked. Other chats stay open.
// ═══════════════════════════════════════════════════

function _lockChatUI(locked) {
  const inp     = document.getElementById("msgInput");
  const sendBtn = document.getElementById("sendBtn");
  const bar     = document.getElementById("genStatusBar");
  const stopBtn = document.getElementById("stopGenBtn");

  if (inp)     inp.disabled    = locked;
  if (sendBtn) sendBtn.disabled = locked;
  if (bar)     bar.style.display = locked ? "" : "none";
  if (stopBtn) stopBtn.style.display = locked ? "" : "none";

  if (locked) {
    if (inp) inp.placeholder = "⏳ Atlas AI is generating a response…";
    if (inp) inp.title = "Please wait until the current response is complete";
  } else {
    if (inp) {
      inp.disabled = false;
      inp.placeholder = "Message Atlas AI… (paste or drop images/files here)";
      inp.title = "";
      inp.focus();
    }
  }
}

function stopGeneration() {
  // Abort in-flight request for current session
  const ctrl = _sessionLocks.get(sessionId);
  if (ctrl) {
    ctrl.abort();
    _sessionLocks.delete(sessionId);
  }
  isWaiting = false;
  _lockChatUI(false);
  toast("Generation stopped");
  // Remove typing indicator if present
  document.querySelectorAll(".typing-bubble").forEach(b => b.parentElement?.remove());
}

// Unlock all sessions on page hide/reload to prevent stuck locks
window.addEventListener("beforeunload", () => {
  _sessionLocks.forEach(ctrl => ctrl.abort());
  _sessionLocks.clear();
});

function fillInp(text) {
  const ta = document.getElementById("msgInput");
  ta.value = text;
  autoResize(ta);
  ta.focus();
}

// ─────────────────────────────────────────────────────────
// SEND MESSAGE
// ─────────────────────────────────────────────────────────
async function sendMsg() {
  if (isWaiting) return;
  // Per-session lock: block if THIS session is already generating
  if (_sessionLocks.has(sessionId)) return;

  const ta  = document.getElementById("msgInput");
  const msg = ta.value.trim();
  if (!msg && !activeAttachment) return;

  if (!hasMessages) {
    sessionName = (msg || activeAttachment?.name || "File").slice(0, 45);
    document.getElementById("chatTitle").textContent = sessionName;
    document.getElementById("welcome").style.display = "none";
    document.getElementById("messages").style.display = "block";
    hasMessages = true;
  }

  // Show user message with optional attachment thumbnail
  _appendUserMsgWithAttachment(msg, activeAttachment);
  ta.value = "";
  autoResize(ta);

  // Capture attachment before clearing
  const attachment = activeAttachment;

  // Clear attachment badge immediately after send (Fix 4)
  clearAttachment();

  const typId = showTyping();
  isWaiting   = true;
  const abortCtrl = new AbortController();
  _sessionLocks.set(sessionId, abortCtrl);
  _lockChatUI(true);

  try {
    // Build request body — include attachment info if present
    const body = {
      message:            msg,
      csv_path:           activeCsv,
      colormap:           selectedCmap,
      session_id:         sessionId,
      session_name:       sessionName,
      project_id:         activeProjectId || null,
    };
    if (attachment) {
      if (attachment.type === "csv") {
        body.csv_path = attachment.path;
      } else {
        body.attached_file_path = attachment.path;
        body.attached_file_type = attachment.type;
        body.attached_file_name = attachment.name;
      }
    }

    const res = await fetch(`${BACKEND}/api/chat/send`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
      signal:  abortCtrl.signal
    });
    const data = await res.json();
    removeTyping(typId);

    if (data.clear_csv || data.clear_attachment) clearCSV(false);
    else if (data.csv_path) activeCsv = data.csv_path;
    if (data.show_sidebar) showMSB();

    if (data.map_url) {
      currentMapId = data.map_id || null;
      currentTitle = msg;
      appendMsgWithMap(data.reply, data.map_url, data.map_id);
      if (mapSBOpen) loadMapHistory();
      hideDatasetBadge();
    } else if (data.error) {
      appendMsgWithErr(data.reply, data.error);
    } else {
      appendMsg("assistant", data.reply);
    }

    // Show uploaded image inline in chat if AI just analyzed one
    if (attachment && attachment.type === "image" && attachment.previewUrl && data.reply && !data.map_url) {
      appendImageCard(attachment.previewUrl, attachment.name);
    }

    if (data.dataset_notice) appendDatasetNotice(data.dataset_notice, data.dataset_meta);
    if (data.has_dataset)    updateDatasetBadge(data.dataset_meta);

    loadChatList();

  } catch (e) {
    removeTyping(typId);
    // Show specific JS error vs network error
    const errMsg = (e instanceof TypeError && e.message.includes("null"))
      ? `❌ UI error: ${e.message}\n\nPlease refresh the page (Ctrl+Shift+R).`
      : e.name === "TimeoutError"
        ? "Request timed out. Map generation can take up to 3 minutes. Please try again."
        : `Cannot reach backend.\n\nMake sure python3 app.py is running on port 5001.\n\n${e.message}`;
    appendMsg("assistant", errMsg);
  } finally {
    isWaiting = false;
    _sessionLocks.delete(sessionId);
    _lockChatUI(false);
  }
}

// ─────────────────────────────────────────────────────────
// MESSAGES
// ─────────────────────────────────────────────────────────
function appendMsg(role, text) {
  const list = document.getElementById("messages");

  // Fix 5: Map messages stored with __MAP__mapId::url prefix — re-render on chat reload
  if (role === "assistant" && text && text.startsWith("__MAP__")) {
    const rest   = text.slice(7);                      // remove "__MAP__"
    const colons = rest.indexOf("::");
    const mapId  = colons > 0 ? rest.slice(0, colons) : "";
    const mapUrl = colons > 0 ? rest.slice(colons + 2) : rest;
    if (mapUrl) {
      if (mapId) { currentMapId = mapId; }
      appendMsgWithMap("", mapUrl, mapId);
      return;
    }
  }

  const div  = document.createElement("div");
  div.className = `msg ${role}`;
  const isUser = role === "user";
  const isPermission = !isUser && text === "This request requires backend map generation.\nAllow execution?\n[YES] [NO]";
  div.innerHTML = `
    <div class="msg-av">${isUser ? "P" : "◈"}</div>
    <div class="msg-body">
      <div class="msg-text">${fmt(text)}</div>
      ${isPermission ? `<div class="perm-row">
        <button class="perm-btn yes" onclick="sendPermission('yes')">YES</button>
        <button class="perm-btn no" onclick="sendPermission('no')">NO</button>
      </div>` : ""}
      <div class="msg-acts">
        <button class="msg-act" onclick="copyMsg(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copy
        </button>
        ${isUser ? `<button class="msg-act" onclick="editMsg(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>Edit
        </button>` : `<button class="msg-act speak-btn" onclick="speakMsg(this)" title="Read aloud">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>
          <span class="speak-label">Read</span>
        </button>`}
      </div>
    </div>`;
  list.appendChild(div);
  scrollBottom();
}

function sendPermission(answer) {
  document.getElementById("msgInput").value = answer;
  sendMsg();
}

function appendMsgWithMap(text, mapUrl, mapId) {
  const list   = document.getElementById("messages");
  const div    = document.createElement("div");
  div.className = "msg assistant";
  const imgSrc = mapUrl.startsWith("http") ? mapUrl : `${BACKEND}${mapUrl}`;
  // Store mapId on element for download
  if (mapId) div.dataset.mapId = mapId;
  div.innerHTML = `
    <div class="msg-av">◈</div>
    <div class="msg-body">
      <div class="msg-text">
        ${text ? `<p>${fmt(text)}</p>` : ""}
        <div class="map-result">
          <img src="${imgSrc}" alt="Choropleth Map"
               onerror="this.parentElement.innerHTML='<p style=padding:14px;color:#e74c3c>Map image not found. It may have been deleted from the server.</p>'"/>
          <div class="map-result-btns">
            <button class="map-btn primary" onclick="openDl()">⬇ Download</button>
            <button class="map-btn" onclick="window.open('${imgSrc}','_blank')">🔍 Full size</button>
            <button class="map-btn" onclick="copyMsg(this)">⎘ Copy text</button>
          </div>
        </div>
      </div>
    </div>`;
  list.appendChild(div);
  scrollBottom();
}

function appendImageCard(imgUrl, filename) {
  // Show uploaded image in assistant area (like map cards)
  const list = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `
    <div class="msg-av">◈</div>
    <div class="msg-body">
      <div class="msg-text">
        <div class="map-result">
          <img src="${imgUrl}" alt="${filename}" style="cursor:zoom-in"
               onclick="openMapFullscreen('${imgUrl}','${filename}')"/>
          <div class="map-result-btns">
            <button class="map-btn" onclick="openMapFullscreen('${imgUrl}','${filename}')">🔍 Full Size</button>
            <button class="map-btn" onclick="window.open('${imgUrl}','_blank')">⬇ Open</button>
          </div>
        </div>
      </div>
    </div>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function appendMsgWithErr(text, error) {
  const list = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `
    <div class="msg-av">◈</div>
    <div class="msg-body">
      <div class="msg-text">
        <p>${fmt(text)}</p>
        <div class="err-box">${error}</div>
      </div>
      <div class="msg-acts">
        <button class="msg-act" onclick="copyMsg(this)">⎘ Copy</button>
      </div>
    </div>`;
  list.appendChild(div);
  scrollBottom();
}

function showTyping() {
  const list = document.getElementById("messages");
  const id   = "typ-" + Date.now();
  const div  = document.createElement("div");
  div.className = "msg assistant"; div.id = id;
  div.innerHTML = `
    <div class="msg-av">◈</div>
    <div class="msg-body">
      <div class="msg-text">
        <div class="tdots"><div class="td"></div><div class="td"></div><div class="td"></div></div>
      </div>
    </div>`;
  list.appendChild(div);
  scrollBottom();
  return id;
}
function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ─────────────────────────────────────────────────────────
// COPY & EDIT
// ─────────────────────────────────────────────────────────
function copyMsg(btn) {
  // Walk up to .msg-body, then find .msg-text
  const body = btn.closest(".msg-body");
  if (!body) return;
  const textEl = body.querySelector(".msg-text");
  if (!textEl) return;

  // Clone node, remove inner buttons/svgs/map-result-btns so we only get text
  const clone = textEl.cloneNode(true);
  clone.querySelectorAll("button, svg, .map-result-btns, .map-result img, .perm-row").forEach(el => el.remove());
  const text = (clone.innerText || clone.textContent || "").trim();

  // Use clipboard API with fallback for http (non-HTTPS) environments
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text)
      .then(() => toast("Copied!"))
      .catch(() => _copyFallback(text));
  } else {
    _copyFallback(text);
  }
}

function _copyFallback(text) {
  // Works on http://localhost where clipboard API may be blocked
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;left:-9999px;top:-9999px;opacity:0";
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try {
    document.execCommand("copy");
    toast("Copied!");
  } catch(e) {
    toast("Copy failed — select text manually");
  }
  document.body.removeChild(ta);
}
function editMsg(btn) {
  editingEl = btn.closest(".msg");
  document.getElementById("editTa").value = editingEl.querySelector(".msg-text").innerText || "";
  document.getElementById("editOverlay").classList.add("show");
}
function closeEdit() {
  document.getElementById("editOverlay").classList.remove("show");
  editingEl = null;
}
function saveEdit() {
  const txt = document.getElementById("editTa").value.trim();
  if (!txt) return;
  if (editingEl) {
    const list = document.getElementById("messages");
    const all  = [...list.querySelectorAll(".msg")];
    const idx  = all.indexOf(editingEl);
    for (let i = idx; i < all.length; i++) all[i].remove();
  }
  closeEdit();
  document.getElementById("msgInput").value = txt;
  sendMsg();
}

// ─────────────────────────────────────────────────────────
// CSV UPLOAD
// ─────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────
// UNIFIED ATTACHMENT SYSTEM
// Single pin icon handles all file types.
// File uploads to server immediately, but is NOT processed until user sends.
// File + typed message go together as one request.
// ─────────────────────────────────────────────────────────

const ATTACH_ICONS = {
  image:"🖼️", pdf:"📄", excel:"📊", docx:"📝",
  text:"📃", csv:"📋", unknown:"📎"
};

async function handleAttachment(event) {
  const file = event.target.files[0];
  if (!file) return;
  event.target.value = "";

  _showAttachBadge("⏳", file.name, false, null);
  toast(`Uploading ${file.name}…`);

  // Create local blob preview URL for images immediately
  const imgExts = ["png","jpg","jpeg","webp","gif","bmp"];
  const fileExt  = file.name.split(".").pop().toLowerCase();
  let localPreviewUrl = imgExts.includes(fileExt) ? URL.createObjectURL(file) : null;

  const fd = new FormData();
  fd.append("file", file);
  try {
    const res  = await fetch(`${BACKEND}/api/files/upload-only`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { toast("Upload failed: " + data.error); _hideAttachBadge(); return; }

    activeAttachment = {
      path:       data.path,
      type:       data.file_type,
      name:       data.name,
      ext:        data.ext,
      icon:       ATTACH_ICONS[data.file_type] || "📎",
      previewUrl: localPreviewUrl,
    };

    if (data.file_type === "csv") {
      activeCsv = data.path;
      const csvBadge = document.getElementById("csvBadgeRow");
      const csvName  = document.getElementById("csvBadgeName");
      if (csvBadge) csvBadge.style.display = "flex";
      if (csvName)  csvName.textContent    = file.name;
    }

    _showAttachBadge(ATTACH_ICONS[data.file_type] || "📎", file.name, true, localPreviewUrl);
    toast(`${file.name} ready — type your message and send`);
  } catch(e) {
    toast("Upload error: " + e.message);
    _hideAttachBadge();
  }
}

function _showAttachBadge(icon, name, ready, previewUrl) {
  const badge  = document.getElementById("attachBadge");
  const iconEl = document.getElementById("attachBadgeIcon");
  const nameEl = document.getElementById("attachBadgeName");
  if (!badge) return;
  if (previewUrl) {
    iconEl.innerHTML = `<img src="${previewUrl}" class="ab-preview-img" alt="preview"/>`;
  } else {
    iconEl.textContent = icon;
  }
  nameEl.textContent  = name;
  badge.style.display = "";
  badge.classList.toggle("ab-ready", ready);
}

function _hideAttachBadge() {
  const badge = document.getElementById("attachBadge");
  if (badge) badge.style.display = "none";
}

function clearAttachment() {
  activeAttachment = null;
  _hideAttachBadge();
  // Also clear CSV if it was an attached CSV
  // (clearCSV handles csvBadgeRow)
}

// ─────────────────────────────────────────────────────────
// PASTE & DRAG-DROP INTO MESSAGE TEXTAREA
// Ctrl+V image, drag image/file — attaches directly to message box
// ─────────────────────────────────────────────────────────

async function handleMsgPaste(event) {
  const items = event.clipboardData?.items;
  if (!items) return;
  for (const item of items) {
    if (item.kind === "file") {
      const file = item.getAsFile();
      if (file) {
        event.preventDefault();
        await _uploadFileAsAttachment(file);
        return;
      }
    }
  }
}

function handleMsgDragOver(event) {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  document.getElementById("msgInput").classList.add("drag-active");
}

function handleMsgDragLeave() {
  document.getElementById("msgInput").classList.remove("drag-active");
}

async function handleMsgDrop(event) {
  event.preventDefault();
  document.getElementById("msgInput").classList.remove("drag-active");
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    await _uploadFileAsAttachment(files[0]);
  }
}

async function _uploadFileAsAttachment(file) {
  const ALLOWED_EXTS = [
    ".csv",".png",".jpg",".jpeg",".webp",".gif",
    ".pdf",".xlsx",".xls",".docx",".doc",".txt",".md",".pptx",".zip"
  ];
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_EXTS.includes(ext)) { toast(`File type ${ext} not supported`); return; }
  const imgExts = [".png",".jpg",".jpeg",".webp",".gif",".bmp"];
  const localPreviewUrl = imgExts.includes(ext) ? URL.createObjectURL(file) : null;
  _showAttachBadge("⏳", file.name, false, null);
  toast(`Attaching ${file.name}…`);
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res  = await fetch(`${BACKEND}/api/files/upload-only`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { toast("Attach failed: " + data.error); _hideAttachBadge(); return; }
    activeAttachment = {
      path: data.path, type: data.file_type,
      name: data.name, ext: data.ext,
      icon: ATTACH_ICONS[data.file_type] || "📎",
      previewUrl: localPreviewUrl,
    };
    if (data.file_type === "csv") {
      activeCsv = data.path;
      const csvBadge = document.getElementById("csvBadgeRow");
      const csvName  = document.getElementById("csvBadgeName");
      if (csvBadge) csvBadge.style.display = "flex";
      if (csvName)  csvName.textContent    = file.name;
    }
    _showAttachBadge(ATTACH_ICONS[data.file_type] || "📎", file.name, true, localPreviewUrl);
    toast(`${file.name} attached — type your message and send`);
  } catch(e) { toast("Attach error: " + e.message); _hideAttachBadge(); }
}

// Show user message with real image preview or file card in the chat bubble
function _appendUserMsgWithAttachment(msg, attachment) {
  const list = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "msg user";

  let attachHtml = "";
  if (attachment) {
    if (attachment.previewUrl && attachment.type === "image") {
      // Real image preview in user bubble
      attachHtml = `
        <div class="attach-thumb at-img-thumb">
          <img src="${attachment.previewUrl}" class="at-preview-img"
               alt="${attachment.name}"
               onclick="window.open('${attachment.previewUrl}','_blank')"/>
          <span class="at-name-below">${attachment.name}</span>
        </div>`;
    } else {
      // File card for non-image types
      const fileColor = {pdf:"#e74c3c",excel:"#27ae60",docx:"#2980b9",
                         text:"#7f8c8d",zip:"#8e44ad",csv:"#16a085"}[attachment.type] || "#555";
      attachHtml = `
        <div class="attach-thumb at-file-thumb">
          <div class="at-file-icon" style="background:${fileColor}">${attachment.icon}</div>
          <div class="at-file-info">
            <div class="at-name">${attachment.name}</div>
            <div class="at-type">${(attachment.ext||"").toUpperCase().replace(".","")}</div>
          </div>
        </div>`;
    }
  }

  div.innerHTML = `
    <div class="msg-av">P</div>
    <div class="msg-body">
      ${attachHtml}
      ${msg ? `<div class="msg-text">${fmt(msg)}</div>` : ""}
      <div class="msg-acts">
        <button class="msg-act" onclick="copyMsg(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copy
        </button>
        <button class="msg-act" onclick="editMsg(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>Edit
        </button>
      </div>
    </div>`;
  list.appendChild(div);
  scrollBottom();
}

// Legacy: uploadCSV still works if called from map sidebar
async function uploadCSV(event) {
  const file = event.target.files[0];
  if (!file) return;
  event.target.value = "";
  const fd = new FormData();
  fd.append("file", file);
  toast("Uploading " + file.name + "...");
  try {
    const res  = await fetch(`${BACKEND}/api/map/upload-csv`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { toast("Error: " + data.error); return; }
    activeCsv = data.csv_path;
    document.getElementById("csvPrevBox").style.display  = "block";
    document.getElementById("cpbName").textContent       = file.name;
    document.getElementById("cpbPrev").textContent       = data.preview;
    document.getElementById("csvBadgeRow").style.display = "flex";
    document.getElementById("csvBadgeName").textContent  = file.name;
    toast(file.name + " attached — " + data.rows + " rows");
  } catch(e) { toast("Upload failed: " + e.message); }
}

async function convertPasted() {
  const text = document.getElementById("pasteArea").value.trim();
  if (!text) { toast("Paste data first"); return; }
  toast("Converting...");
  try {
    const res  = await fetch(`${BACKEND}/api/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "convert", pasted_data: text,
                             colormap: selectedCmap, session_id: sessionId, session_name: sessionName })
    });
    const data = await res.json();
    if (data.csv_path) {
      activeCsv = data.csv_path;
      document.getElementById("csvBadgeRow").style.display  = "flex";
      document.getElementById("csvBadgeName").textContent   = "pasted_data.csv";
      document.getElementById("pasteArea").value = "";
      toast("Data ready — ask me to generate a map!");
    }
  } catch (e) { toast("Failed: " + e.message); }
}

function clearCSV(showToast = true) {
  activeCsv = null;
  const csvBadge = document.getElementById("csvBadgeRow");
  const csvPrev  = document.getElementById("csvPrevBox");
  const inp      = document.getElementById("attachInput") || document.getElementById("csvUpload");
  if (csvBadge) csvBadge.style.display = "none";
  if (csvPrev)  csvPrev.style.display  = "none";
  if (inp)      inp.value = "";
  if (showToast) toast("CSV cleared");
}

// ─────────────────────────────────────────────────────────
// DOWNLOAD
// ─────────────────────────────────────────────────────────
function openDl()  { document.getElementById("dlOverlay").classList.add("show"); }
function closeDl() { document.getElementById("dlOverlay").classList.remove("show"); }
async function dlFmt(fmt) {
  const t = encodeURIComponent(currentTitle || "choropleth_map");
  const i = currentMapId ? `&id=${currentMapId}` : "";
  toast("Downloading ." + fmt.toUpperCase()); closeDl();
  try {
    const res  = await fetch(`${BACKEND}/api/map/download?format=${fmt}&title=${t}${i}`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `${currentTitle || "choropleth_map"}.${fmt}`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) { toast("Download failed: " + e.message); }
}
async function dlCSV() {
  if (!currentMapId) { toast("No map CSV snapshot selected"); return; }
  toast("Downloading map CSV snapshot"); closeDl();
  try {
    const res  = await fetch(`${BACKEND}/api/map/download-csv?id=${currentMapId}`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `map_${currentMapId}.csv`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) { toast("Download failed: " + e.message); }
}

// ─────────────────────────────────────────────────────────
// CHAT LIST (sidebar)
// ─────────────────────────────────────────────────────────
async function loadChatList() {
  try {
    const res   = await fetch(`${BACKEND}/api/chat/recent`);
    const chats = await res.json();
    const list  = document.getElementById("chatList");
    if (!chats.length) {
      list.innerHTML = `<div class="no-chats">No conversations yet</div>`;
      return;
    }
    list.innerHTML = chats.map(c => `
      <div class="chat-item ${c.id === sessionId ? "active" : ""}" onclick="loadChat('${c.id}','${c.name || "Chat"}')">
        <div class="ci-name">${c.name || "Untitled"}</div>
        <div class="ci-time">${c.updated || c.created || ""}</div>
        <div class="ci-actions">
          <button class="ci-act" onclick="event.stopPropagation();openMoveChat('${c.id}')">Move to project</button>
          <button class="ci-act" onclick="event.stopPropagation();deleteChat('${c.id}')">Delete</button>
        </div>
      </div>`).join("");
  } catch {}
}

async function loadChat(id, name) {
  try {
    const res  = await fetch(`${BACKEND}/api/chat/get/${id}`);
    const data = await res.json();
    sessionId        = id;
    sessionName      = name;
    hasMessages      = true;
    activeProjectId  = data.project_id || null;

    document.getElementById("chatTitle").textContent     = name;
    document.getElementById("welcome").style.display     = "none";
    document.getElementById("messages").style.display    = "block";
    document.getElementById("messages").innerHTML        = "";

    (data.messages || []).forEach(m => appendMsg(m.role, m.content));
    scrollBottom();
    switchView("chat", document.querySelector(".nav-item"));
  } catch {}
}

async function searchChats(q) {
  if (!q.trim()) { loadChatList(); return; }
  try {
    const res   = await fetch(`${BACKEND}/api/chat/search?q=${encodeURIComponent(q)}`);
    const chats = await res.json();
    const list  = document.getElementById("chatList");
    if (!chats.length) {
      list.innerHTML = `<div class="no-chats">No results for "${q}"</div>`;
      return;
    }
    const hl = (str) => {
      if (!str) return "";
      const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")})`, "gi");
      return str.replace(re, `<mark class="srch-hl">$1</mark>`);
    };
    list.innerHTML = `<div class="srch-label">Results for "${q}"</div>` +
      chats.map(c => `
        <div class="chat-item" onclick="loadChat('${c.id}','${(c.name||'Chat').replace(/'/g,"\\'")}')">
          <div class="ci-name">${hl(c.name || "Untitled")}</div>
          <div class="ci-time">${c.updated || ""}</div>
        </div>`).join("");
  } catch {}
}

async function deleteChat(id) {
  if (!confirm("Delete this chat?")) return;
  await fetch(`${BACKEND}/api/chat/delete/${id}`, { method: "DELETE" });
  if (id === sessionId) newChat();
  else { loadChatList(); }
  toast("Chat deleted");
}

function newChat() {
  sessionId       = 'sess_' + Date.now();
  sessionName     = 'New Chat';
  hasMessages     = false;
  activeCsv       = null;
  currentMapId    = null;
  activeProjectId = null;

  document.getElementById("chatTitle").textContent       = "Atlas AI";
  document.getElementById("welcome").style.display       = "flex";
  document.getElementById("messages").style.display      = "none";
  document.getElementById("messages").innerHTML          = "";
  document.getElementById("csvBadgeRow").style.display   = "none";
  document.getElementById("csvPrevBox").style.display    = "none";
  document.getElementById("mapTogBtn").style.display     = "none";
  mapSBOpen = false;
  document.getElementById("mapSidebar").classList.remove("open");

  switchView("chat", document.querySelector(".nav-item"));
  loadChatList(); // single refresh after state reset
}

// ─────────────────────────────────────────────────────────
// MOVE CHAT TO PROJECT
// ─────────────────────────────────────────────────────────
async function openMoveChat(chatId) {
  moveChatId  = chatId;
  moveProjSel = null;
  document.getElementById("moveChatOverlay").classList.add("show");

  const res      = await fetch(`${BACKEND}/api/project/list`);
  const projects = await res.json();
  const list     = document.getElementById("moveProjList");

  list.innerHTML = `
    <button class="move-proj-opt recent-opt" onclick="selectMoveTarget(this, null)">
      <span>📋</span> Recent Chats (remove from project)
    </button>` +
    projects.map(p => `
      <button class="move-proj-opt" onclick="selectMoveTarget(this,'${p.id}')">
        <span>${p.icon || "📁"}</span> ${p.title}
      </button>`).join("");
}

function selectMoveTarget(el, projId) {
  document.querySelectorAll(".move-proj-opt").forEach(b => b.classList.remove("selected"));
  el.classList.add("selected");
  moveProjSel = projId;
}

async function confirmMoveChat() {
  if (!moveChatId) { closeMoveChat(); return; }
  try {
    const res = await fetch(`${BACKEND}/api/project/move-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: moveChatId, project_id: moveProjSel })
    });
    const data = await res.json();
    if (data.ok) {
      toast(moveProjSel ? "Chat moved to project!" : "Chat moved to Recent");
      loadChatList();
      loadSBProjects();
      if (currentProjId) loadProjectChats(currentProjId);
    }
  } catch (e) { toast("Move failed: " + e.message); }
  closeMoveChat();
}

function closeMoveChat() {
  document.getElementById("moveChatOverlay").classList.remove("show");
  moveChatId  = null;
  moveProjSel = null;
}

// ─────────────────────────────────────────────────────────
// MAP HISTORY
// ─────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────
// MAP SIDEBAR HISTORY (chat sidebar panel)
// View only — no paste into chat, no map reuse
// ─────────────────────────────────────────────────────────
async function loadMapHistory() {
  try {
    const res  = await fetch(`${BACKEND}/api/map/history`);
    const hist = await res.json();
    const list = document.getElementById("mapHistList");
    if (!hist.length) { list.innerHTML = `<div class="empty-state">No maps yet</div>`; return; }
    list.innerHTML = hist.map(h => `
      <div class="mhc">
        <img src="${BACKEND}/storage/history/${h.map_file}?nocache=${h.id}"
             onerror="this.style.display='none'" loading="lazy"/>
        <div class="mhc-info">
          <div class="mhc-title">${h.title || "Untitled"}</div>
          <div class="mhc-meta">${h.colormap || ""} · ${(h.timestamp||"").slice(0,16)}</div>
        </div>
        <div class="mhc-btns">
          <button class="mhc-dl" onclick="histDl('${h.id}','${encodeURIComponent(h.title||'map')}','png')">⬇PNG</button>
          <button class="mhc-dl" onclick="histDl('${h.id}','${encodeURIComponent(h.title||'map')}','csv')">⬇CSV</button>
        </div>
      </div>`).join("");
  } catch(e) { console.error("loadMapHistory:",e); }
}

async function histDl(mapId, title, fmt) {
  try {
    const t   = encodeURIComponent(decodeURIComponent(title));
    const url = fmt === "csv"
      ? `${BACKEND}/api/map/download-csv?id=${mapId}`
      : `${BACKEND}/api/map/download?format=${fmt}&title=${t}&id=${mapId}`;
    const res  = await fetch(url);
    const blob = await res.blob();
    const a    = document.createElement("a");
    a.href     = URL.createObjectURL(blob);
    a.download = `${decodeURIComponent(title)}.${fmt}`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`Downloading .${fmt.toUpperCase()}`);
  } catch(e) { toast("Download failed: " + e.message); }
}

// ─────────────────────────────────────────────────────────
// MAPS VIEW — 2 TABS
// ─────────────────────────────────────────────────────────
function switchMapsTab(tab) {
  document.getElementById("mapsTabHistory").style.display = tab === "history" ? "" : "none";
  document.getElementById("mapsTabManual").style.display  = tab === "manual"  ? "" : "none";
  document.getElementById("tabHistBtn").classList.toggle("active",   tab === "history");
  document.getElementById("tabManualBtn").classList.toggle("active",  tab === "manual");
  if (tab === "history") loadMapsView();
}

async function loadMapsView() {
  try {
    const res  = await fetch(`${BACKEND}/api/map/history`);
    const hist = await res.json();
    const grid = document.getElementById("mapsGrid");
    if (!hist.length) {
      grid.innerHTML = `<div class="empty-state" style="text-align:center;padding:60px 20px">
        <div style="font-size:40px;margin-bottom:12px">🗺️</div>
        <div style="font-size:15px;font-weight:600;margin-bottom:6px">No maps yet</div>
        <div style="font-size:13px;color:var(--muted)">Go to Chat and ask Atlas AI to generate a choropleth map,<br>or use the Manual Generation tab above.</div>
      </div>`;
      return;
    }
    grid.innerHTML = hist.map(h => `
      <div class="map-card">
        <img src="${BACKEND}/storage/history/${h.map_file}?nocache=${h.id}"
             onerror="this.src=''" loading="lazy"
             onclick="openMapFullscreen('${BACKEND}/storage/history/${h.map_file}?nocache=${h.id}','${(h.title||'Map').replace(/'/g,"\\'")}')"
             style="cursor:zoom-in" title="Click to view full screen"/>
        <div class="mc-info">
          <div class="mc-title">${h.title || "Untitled"}</div>
          <div class="mc-meta">${h.colormap||""} · ${h.value_col||""} · ${(h.timestamp||"").slice(0,16)}</div>
        </div>
        <div class="mc-btns">
          <button class="mc-dl-btn mc-view-btn" onclick="openMapFullscreen('${BACKEND}/storage/history/${h.map_file}?nocache=${h.id}','${(h.title||'Map').replace(/'/g,"\\'")}')">🔍 Full View</button>
          <button class="mc-dl-btn" onclick="histDl('${h.id}','${encodeURIComponent(h.title||'map')}','png')">⬇ PNG</button>
          <button class="mc-dl-btn" onclick="histDl('${h.id}','${encodeURIComponent(h.title||'map')}','pdf')">⬇ PDF</button>
          <button class="mc-dl-btn" onclick="histDl('${h.id}','${encodeURIComponent(h.title||'map')}','csv')">⬇ CSV</button>
        </div>
      </div>`).join("");
  } catch(e) { console.error("loadMapsView:",e); }
}

function openMapFullscreen(imgUrl, title) {
  // Remove any existing fullscreen overlay
  const existing = document.getElementById("mapFsOverlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "mapFsOverlay";
  overlay.className = "map-fs-overlay";
  overlay.innerHTML = `
    <div class="map-fs-toolbar">
      <span class="map-fs-title">${title}</span>
      <div class="map-fs-actions">
        <button onclick="window.open('${imgUrl}','_blank')" class="map-fs-btn">↗ Open Original</button>
        <button onclick="document.getElementById('mapFsOverlay').remove()" class="map-fs-btn map-fs-close">✕ Close</button>
      </div>
    </div>
    <div class="map-fs-body">
      <img src="${imgUrl}" alt="${title}" class="map-fs-img" onclick="event.stopPropagation()"/>
    </div>`;
  overlay.onclick = () => overlay.remove();
  document.body.appendChild(overlay);
}

// ─────────────────────────────────────────────────────────
// MANUAL GENERATION TAB
// ─────────────────────────────────────────────────────────
let mgpCsvPath = null;
let mgpMapId   = null;

function mgpDragOver(e) {
  e.preventDefault();
  document.getElementById("mgpDropZone").classList.add("mgp-drag-over");
}
function mgpDragLeave() {
  document.getElementById("mgpDropZone").classList.remove("mgp-drag-over");
}
function mgpDrop(e) {
  e.preventDefault();
  document.getElementById("mgpDropZone").classList.remove("mgp-drag-over");
  const file = e.dataTransfer?.files?.[0];
  if (file) _mgpUpload(file);
}
function mgpFileChosen(e) {
  const file = e.target.files?.[0];
  if (file) _mgpUpload(file);
}
async function _mgpUpload(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) { toast("Please upload a .csv file"); return; }
  const fd = new FormData();
  fd.append("file", file);
  mgpStatus("⏳ Uploading…", false);
  try {
    const res  = await fetch(`${BACKEND}/api/map/upload-csv`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { mgpStatus("⚠️ " + data.error, true); return; }
    mgpCsvPath = data.csv_path;
    document.getElementById("mgpFileName").textContent  = file.name;
    document.getElementById("mgpRowCount").textContent  = `${data.rows} data rows`;
    document.getElementById("mgpPreviewText").textContent = data.preview || "";
    document.getElementById("mgpPreviewBox").style.display = "";
    document.getElementById("mgpDropZone").style.display   = "none";
    document.getElementById("mgpPasteArea").value = "";
    document.getElementById("mgpParseBtn").disabled = true;
    document.getElementById("mgpGenBtn").disabled = false;
    document.getElementById("mgpResult").style.display = "none";
    mgpStatus("✅ File loaded. Set title and colour, then click Generate Map.", false);
    toast("CSV ready");
  } catch(e) { mgpStatus("⚠️ Upload failed: " + e.message, true); }
}
function mgpClearFile() {
  mgpCsvPath = null; mgpMapId = null;
  document.getElementById("mgpPreviewBox").style.display = "none";
  document.getElementById("mgpDropZone").style.display   = "";
  document.getElementById("mgpFileInput").value = "";
  document.getElementById("mgpGenBtn").disabled = true;
  document.getElementById("mgpResult").style.display = "none";
  mgpStatus("", false);
}
function mgpPasteChanged() {
  const has = document.getElementById("mgpPasteArea").value.trim().length > 0;
  document.getElementById("mgpParseBtn").disabled = !has;
}
async function mgpParsePasted() {
  const text = document.getElementById("mgpPasteArea").value.trim();
  if (!text) { toast("Paste some data first"); return; }
  // Save pasted data as CSV via existing csv_handler endpoint
  try {
    const fd = new FormData();
    const blob = new Blob([text], { type: "text/csv" });
    fd.append("file", blob, "pasted_data.csv");
    mgpStatus("⏳ Parsing pasted data…", false);
    const res  = await fetch(`${BACKEND}/api/map/upload-csv`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { mgpStatus("⚠️ " + data.error, true); return; }
    mgpCsvPath = data.csv_path;
    document.getElementById("mgpPreviewBox").style.display = "";
    document.getElementById("mgpFileName").textContent  = "Pasted data";
    document.getElementById("mgpRowCount").textContent  = `${data.rows} rows`;
    document.getElementById("mgpPreviewText").textContent = data.preview || text.slice(0,200);
    document.getElementById("mgpDropZone").style.display   = "none";
    document.getElementById("mgpGenBtn").disabled = false;
    document.getElementById("mgpResult").style.display = "none";
    mgpStatus("✅ Data parsed. Click Generate Map.", false);
  } catch(e) { mgpStatus("⚠️ Parse failed: " + e.message, true); }
}
async function mgpGenerate() {
  if (!mgpCsvPath) { toast("Upload or paste CSV data first"); return; }

  // ── PERMISSION GATE — ask before sending data to backend ──────────────
  const permitted = await _mgpAskPermission();
  if (!permitted) return;

  const btn = document.getElementById("mgpGenBtn");
  btn.disabled = true; btn.textContent = "⏳ Generating map…";
  mgpStatus("🔄 Running Python map generation code… this may take 30–60 seconds.", false);
  document.getElementById("mgpResult").style.display = "none";
  try {
    const res  = await fetch(`${BACKEND}/api/map/generate-from-upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        csv_path:   mgpCsvPath,
        colormap:   document.getElementById("mgpColormap").value || "Blues",
        title:      document.getElementById("mgpTitle").value.trim() || "Choropleth Map",
        session_id: "manual_gen",
      }),
      signal: AbortSignal.timeout(150000),
    });
    const data = await res.json();
    if (data.error) {
      mgpStatus("⚠️ Generation failed:\n" + data.error, true);
    } else {
      mgpMapId = data.map_id;
      const img = document.getElementById("mgpResultImg");
      img.src = `${BACKEND}${data.map_url}`;
      document.getElementById("mgpResult").style.display = "";
      mgpStatus("✅ Map generated successfully from your data.", false);
      if (mapSBOpen) loadMapHistory();
      loadMapsView();
    }
  } catch(e) {
    mgpStatus(
      e.name === "TimeoutError"
        ? "⚠️ Timed out (>2.5 min). Try a smaller CSV or check your Ollama server."
        : "⚠️ Error: " + e.message,
      true
    );
  }
  btn.disabled = false; btn.textContent = "🗺️ Generate Map";
}

/**
 * Show a permission dialog in the manual generation panel.
 * Returns a Promise<boolean> — true if user clicked YES, false if NO.
 */
function _mgpAskPermission() {
  return new Promise((resolve) => {
    // Remove any existing dialog
    const existing = document.getElementById("mgpPermDialog");
    if (existing) existing.remove();

    const dlg = document.createElement("div");
    dlg.id = "mgpPermDialog";
    dlg.className = "mgp-perm-dialog";
    dlg.innerHTML = `
      <div class="mgp-perm-inner">
        <div class="mgp-perm-msg">
          🔐 This will send your CSV data to the backend Python map engine for processing.<br>
          Allow execution?
        </div>
        <div class="mgp-perm-btns">
          <button class="perm-btn yes" id="mgpPermYes">YES</button>
          <button class="perm-btn no"  id="mgpPermNo">NO</button>
        </div>
      </div>`;

    // Insert before generate button
    const genBtn = document.getElementById("mgpGenBtn");
    genBtn.parentNode.insertBefore(dlg, genBtn);

    document.getElementById("mgpPermYes").onclick = () => { dlg.remove(); resolve(true); };
    document.getElementById("mgpPermNo").onclick  = () => {
      dlg.remove();
      mgpStatus("❌ Map generation cancelled. Permission denied.", true);
      resolve(false);
    };
  });
}
async function mgpDownload(fmt) {
  if (!mgpMapId) { toast("Generate a map first"); return; }
  const title = document.getElementById("mgpTitle").value.trim() || "map";
  await histDl(mgpMapId, title, fmt);
}
function mgpStatus(msg, isError) {
  const el = document.getElementById("mgpStatus");
  if (!msg) { el.style.display = "none"; return; }
  el.style.display = "";
  el.textContent   = msg;
  el.className     = "mgp-status" + (isError ? " mgp-status-err" : "");
}



// ─────────────────────────────────────────────────────────
// PROJECTS — Sidebar list
// ─────────────────────────────────────────────────────────
async function loadSBProjects() {
  try {
    const res      = await fetch(`${BACKEND}/api/project/list`);
    const projects = await res.json();
    const list     = document.getElementById("sbProjList");
    if (!projects.length) { list.innerHTML = ""; return; }
    list.innerHTML = projects.map(p => `
      <div class="proj-sb-item ${p.id === currentProjId ? "active" : ""}"
           onclick="openProjectFromSB('${p.id}')">
        <span class="psi-icon">${p.icon || "📁"}</span>
        <span class="psi-name">${p.title}</span>
        <span class="psi-count">${p.chat_count || 0}</span>
      </div>`).join("");
  } catch {}
}

async function openProjectFromSB(projId) {
  switchView("projects", document.querySelectorAll(".nav-item")[1]);
  await loadProjectsList();
  selectProject(projId);
}

// ─────────────────────────────────────────────────────────
// PROJECTS — Main view
// ─────────────────────────────────────────────────────────
async function loadProjectsList() {
  try {
    const res      = await fetch(`${BACKEND}/api/project/list`);
    const projects = await res.json();
    const items    = document.getElementById("projItems");

    if (!projects.length) {
      items.innerHTML = `<div class="empty-state">No projects yet.<br>Click "+ New" to create one.</div>`;
      return;
    }

    items.innerHTML = projects.map(p => `
      <div class="proj-item ${p.id === currentProjId ? "active" : ""}"
           onclick="selectProject('${p.id}')">
        <span class="pi-icon">${p.icon || "📁"}</span>
        <div class="pi-info">
          <div class="pi-name">${p.title}</div>
          <div class="pi-meta">${p.chat_count || 0} chats · ${p.updated || p.created}</div>
        </div>
      </div>`).join("");
  } catch {}
}

async function selectProject(projId) {
  currentProjId = projId;

  // Mark active in list
  document.querySelectorAll(".proj-item").forEach(el => {
    el.classList.toggle("active", el.onclick.toString().includes(projId));
  });

  // Load project data
  const res  = await fetch(`${BACKEND}/api/project/get/${projId}`);
  const proj = await res.json();

  // Show detail panel
  document.getElementById("projNoSel").style.display  = "none";
  const detail = document.getElementById("projDetail");
  detail.style.display = "flex";

  document.getElementById("pdIcon").textContent  = proj.icon || "📁";
  document.getElementById("pdTitle").textContent = proj.title;

  // Pre-fill settings
  document.getElementById("settingsProjName").value = proj.title;
  document.getElementById("settingsPrompt").value   = proj.system_prompt || "";
  document.getElementById("settingsMemory").value   = proj.memory || "";

  // Load chats tab
  await loadProjectChats(projId);
  await loadProjectDocs(projId);
}

// Project tabs
function projTab(name, btn) {
  document.querySelectorAll(".proj-tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll(".proj-tab-panel").forEach(p => p.classList.remove("active"));
  document.getElementById("ptab-" + name).classList.add("active");
}

async function loadProjectChats(projId) {
  try {
    const res   = await fetch(`${BACKEND}/api/project/chats/${projId}`);
    const chats = await res.json();
    const list  = document.getElementById("projChatsList");

    if (!chats.length) {
      list.innerHTML = `
        <div class="proj-empty-chats">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <p>No chats in this project yet.</p>
          <button class="pci-new-btn" onclick="openChatInProject()">+ Start New Chat</button>
        </div>`;
      return;
    }

    // Click anywhere on chat item to open it (like ChatGPT)
    list.innerHTML =
      `<button class="pci-new-top-btn" onclick="openChatInProject()">+ New Chat in Project</button>` +
      `<div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">` +
      chats.map(c => `
        <div class="proj-chat-item" onclick="openProjChat('${c.id}','${(c.name||'Chat').replace(/'/g,"\\'")}')">
          <div class="pci-left">
            <div class="pci-name">${c.name || "Untitled"}</div>
            <div class="pci-time">${c.updated || ""}</div>
          </div>
          <button class="pci-remove" title="Remove from project"
            onclick="event.stopPropagation();removeChatFromProj('${c.id}')">✕</button>
        </div>`).join("") +
      `</div>`;
  } catch {}
}

async function loadProjectDocs(projId) {
  try {
    const res  = await fetch(`${BACKEND}/api/project/docs/list/${projId}`);
    const docs = await res.json();
    const list = document.getElementById("projDocsList");

    if (!docs.length) {
      list.innerHTML = `<div class="empty-state">No documents uploaded yet.</div>`;
      return;
    }

    const extIcon = { ".pdf":"📄",".txt":"📝",".md":"📝",".docx":"📃",".csv":"📊" };
    list.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px">` +
      docs.map(d => `
        <div class="doc-item">
          <span class="doc-icon">${extIcon[d.ext] || "📄"}</span>
          <div class="doc-info">
            <div class="doc-name">${d.name}</div>
            <div class="doc-meta">${(d.size/1024).toFixed(1)} KB · ${d.uploaded}</div>
          </div>
          <button class="doc-del" onclick="deleteProjDoc('${projId}','${d.id}','${d.name}')">Delete</button>
        </div>`).join("") + `</div>`;
  } catch {}
}

// Open a project chat in chat view
async function openProjChat(chatId, chatName) {
  activeProjectId = currentProjId;  // tie this chat to its project
  await loadChat(chatId, chatName);
}

// New chat within project context
function openChatInProject() {
  if (!currentProjId) return;

  // Set this project as the active project for the new chat
  activeProjectId = currentProjId;

  // Generate a fresh session so it's truly a new chat
  const projTitle = document.getElementById("pdTitle")?.textContent || "Project";
  sessionName  = `${projTitle} Chat`;
  sessionId    = "sess_" + Date.now();
  activeCsv    = null;
  hasMessages  = false;
  clearAttachment();

  // Reset chat UI
  const chatTitle = document.getElementById("chatTitle");
  const welcome   = document.getElementById("welcome");
  const messages  = document.getElementById("messages");
  if (chatTitle) chatTitle.textContent = sessionName;
  if (welcome)   welcome.style.display  = "";
  if (messages) { messages.innerHTML = ""; messages.style.display = "none"; }

  // Switch to chat view
  switchView("chat", document.querySelector(".nav-item"));
  toast(`New chat started in ${projTitle}`);
}

async function removeChatFromProj(chatId) {
  if (!confirm("Remove this chat from the project? It will move to Recent Chats.")) return;
  try {
    const res = await fetch(`${BACKEND}/api/project/remove-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId })
    });
    const data = await res.json();
    if (data.ok) {
      toast("Chat moved to Recent Chats");
      loadProjectChats(currentProjId);
      loadChatList();
    }
  } catch (e) { toast("Error: " + e.message); }
}

async function uploadProjDoc(event) {
  if (!currentProjId) return;
  const file = event.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  toast("Uploading document...");
  try {
    const res  = await fetch(`${BACKEND}/api/project/docs/upload/${currentProjId}`, { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { toast("Error: " + data.error); return; }
    toast(`${file.name} uploaded!`);
    loadProjectDocs(currentProjId);
    event.target.value = "";
  } catch (e) { toast("Upload failed: " + e.message); }
}

async function deleteProjDoc(projId, docId, name) {
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    await fetch(`${BACKEND}/api/project/docs/delete/${projId}/${docId}`, { method:"DELETE" });
    toast("Document deleted");
    loadProjectDocs(projId);
  } catch (e) { toast("Error: " + e.message); }
}

// Project settings actions
async function saveProjName() {
  if (!currentProjId) return;
  const name = document.getElementById("settingsProjName").value.trim();
  if (!name) { toast("Enter a project name"); return; }
  await fetch(`${BACKEND}/api/project/update/${currentProjId}`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ title: name })
  });
  document.getElementById("pdTitle").textContent = name;
  toast("Project renamed!");
  loadSBProjects();
}

async function saveSystemPrompt() {
  if (!currentProjId) return;
  const prompt = document.getElementById("settingsPrompt").value.trim();
  await fetch(`${BACKEND}/api/project/update-prompt/${currentProjId}`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ system_prompt: prompt })
  });
  toast("AI instructions saved!");
}

async function saveMemory() {
  if (!currentProjId) return;
  const memory = document.getElementById("settingsMemory").value.trim();
  await fetch(`${BACKEND}/api/project/update/${currentProjId}`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ memory: memory })
  });
  toast("Project memory saved!");
}

async function deleteProject() {
  const name = document.getElementById("pdTitle").textContent;
  if (!confirm(`Delete project "${name}" and all its data? Chats will be moved to Recent.`)) return;
  await fetch(`${BACKEND}/api/project/delete/${currentProjId}`, { method:"DELETE" });
  currentProjId = null;
  document.getElementById("projNoSel").style.display = "flex";
  document.getElementById("projDetail").style.display = "none";
  toast("Project deleted");
  loadProjectsList(); loadSBProjects(); loadChatList();
}

// Create project
function openCreateProj() {
  document.getElementById("createProjOverlay").classList.add("show");
  document.getElementById("projNameInp").focus();
}
function closeCreateProj() {
  document.getElementById("createProjOverlay").classList.remove("show");
  document.getElementById("projNameInp").value = "";
  document.getElementById("projDescTa").value  = "";
}
function selIcon(btn, icon) {
  document.querySelectorAll(".pib").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  projIcon = icon;
}
async function createProj() {
  const name = document.getElementById("projNameInp").value.trim();
  if (!name) { toast("Enter a project name"); return; }
  const desc = document.getElementById("projDescTa").value.trim();
  try {
    const res  = await fetch(`${BACKEND}/api/project/create`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ title:name, description:desc, icon:projIcon })
    });
    const proj = await res.json();
    closeCreateProj();
    toast("Project created!");
    await loadProjectsList();
    selectProject(proj.id);
    loadSBProjects();
  } catch (e) { toast("Failed: " + e.message); }
}

// ─────────────────────────────────────────────────────────
// NOTES
// ─────────────────────────────────────────────────────────
async function loadNotesView() {
  try {
    const res   = await fetch(`${BACKEND}/api/study/notes/list`);
    const notes = await res.json();
    const list  = document.getElementById("notesList");
    if (!notes.length) { list.innerHTML = `<div class="empty-state">No notes yet</div>`; return; }
    list.innerHTML = notes.map(n => `
      <div class="note-item ${n.id === activeNoteId ? "active" : ""}"
           onclick="openNote('${n.id}','${encodeURIComponent(n.title)}','${encodeURIComponent(n.content)}')">
        <div class="ni-title">${n.title}</div>
        <div class="ni-prev">${n.content}</div>
      </div>`).join("");
  } catch {}
}

function newNote() {
  activeNoteId = null;
  document.getElementById("noteTitleInp").value   = "";
  document.getElementById("noteContentTa").value  = "";
  document.getElementById("noteTitleInp").focus();
}

function openNote(id, title, content) {
  activeNoteId = id;
  document.getElementById("noteTitleInp").value  = decodeURIComponent(title);
  document.getElementById("noteContentTa").value = decodeURIComponent(content);
  document.querySelectorAll(".note-item").forEach(n => n.classList.remove("active"));
  event.currentTarget.classList.add("active");
}

async function saveNote() {
  const title   = document.getElementById("noteTitleInp").value.trim();
  const content = document.getElementById("noteContentTa").value.trim();
  if (!title) { toast("Enter a note title"); return; }
  await fetch(`${BACKEND}/api/study/notes/save`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ title, content })
  });
  loadNotesView();
  toast("Note saved!");
}

// ─────────────────────────────────────────────────────────
// STUDY TOOLS
// ─────────────────────────────────────────────────────────
async function genMCQ() {
  const topic = document.getElementById("mcqTopic").value.trim();
  const count = document.getElementById("mcqCount").value;
  if (!topic) { toast("Enter a topic"); return; }
  const box = document.getElementById("mcqResult");
  box.style.display = "block"; box.textContent = "Generating...";
  try {
    const res  = await fetch(`${BACKEND}/api/study/generate-mcq`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ topic, count: parseInt(count) })
    });
    const data = await res.json();
    box.textContent = data.mcqs || data.error || "No result";
  } catch (e) { box.textContent = "Failed. Check backend is running."; }
}

async function genAssign() {
  const topic = document.getElementById("assignTopic").value.trim();
  const type  = document.getElementById("assignType").value;
  if (!topic) { toast("Enter a topic"); return; }
  const box = document.getElementById("assignResult");
  box.style.display = "block"; box.textContent = "Generating...";
  try {
    const res  = await fetch(`${BACKEND}/api/study/generate-assignment`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ topic, type })
    });
    const data = await res.json();
    box.textContent = data.assignment || data.error || "No result";
  } catch (e) { box.textContent = "Failed. Check backend is running."; }
}

async function explainIt() {
  const topic = document.getElementById("explainTopic").value.trim();
  const level = document.getElementById("explainLevel").value;
  if (!topic) { toast("Enter a topic"); return; }
  const box = document.getElementById("explainResult");
  box.style.display = "block"; box.textContent = "Generating...";
  try {
    const res  = await fetch(`${BACKEND}/api/study/explain`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ topic, level })
    });
    const data = await res.json();
    box.textContent = data.explanation || data.error || "No result";
  } catch (e) { box.textContent = "Failed. Check backend is running."; }
}

// ─────────────────────────────────────────────────────────
// POMODORO TIMER
// ─────────────────────────────────────────────────────────
function startTimer() {
  if (timerRun) {
    clearInterval(timerIv); timerRun = false;
    document.getElementById("timerBtn").textContent = "Start";
    return;
  }
  timerRun = true;
  document.getElementById("timerBtn").textContent = "Pause";
  timerIv = setInterval(() => {
    timerSecs--;
    if (timerSecs <= 0) {
      clearInterval(timerIv); timerRun = false;
      timerSecs = 5 * 60;
      document.getElementById("timerLbl").textContent  = "Break Time! 🎉";
      document.getElementById("timerDisp").textContent = "05:00";
      document.getElementById("timerBtn").textContent  = "Start";
      toast("Focus session done! Take a 5-minute break.");
      return;
    }
    const m = String(Math.floor(timerSecs/60)).padStart(2,"0");
    const s = String(timerSecs % 60).padStart(2,"0");
    document.getElementById("timerDisp").textContent = `${m}:${s}`;
  }, 1000);
}
function resetTimer() {
  clearInterval(timerIv); timerRun = false;
  timerSecs = 25 * 60;
  document.getElementById("timerDisp").textContent = "25:00";
  document.getElementById("timerLbl").textContent  = "Focus Session";
  document.getElementById("timerBtn").textContent  = "Start";
}

// ─────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────
function handleKey(e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMsg(); }
}
function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 200) + "px";
}
function scrollBottom() {
  const m = document.getElementById("messages");
  m.scrollTop = m.scrollHeight;
}
function fmt(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g,     "<em>$1</em>")
    .replace(/`(.*?)`/g,       "<code>$1</code>")
    .replace(/\n/g,            "<br>");
}
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent  = msg;
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 2600);
}

// ─────────────────────────────────────────────────────────
// DATASET BADGE + STATEFUL MEMORY UI
// ─────────────────────────────────────────────────────────

let _badgePollTimer = null;

function updateDatasetBadge(meta) {
  const badge = document.getElementById("datasetBadge");
  const label = document.getElementById("datasetBadgeLabel");
  if (!badge || !label) return;
  if (!meta) { badge.style.display = "none"; return; }
  const rows  = meta.rows  || 0;
  const cols  = (meta.columns || []).join(", ");
  const scope = meta.geo_scope ? ` · ${meta.geo_scope}` : "";
  label.textContent = `${rows} rows${scope}`;
  label.title       = `Columns: ${cols}`;
  badge.style.display = "";
}

function hideDatasetBadge() {
  const badge = document.getElementById("datasetBadge");
  if (badge) badge.style.display = "none";
}

function appendDatasetNotice(notice, meta) {
  // Show a subtle notice below the assistant message
  const list = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "dataset-notice";
  div.innerHTML = `
    <div class="dn-inner">
      <span class="dn-text">${notice}</span>
      <button class="dn-map-btn" onclick="sendQuickMap()">🗺️ Generate Map Now</button>
    </div>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function sendQuickMap() {
  // Inject "Generate choropleth map for above data" into chat
  const inp = document.getElementById("msgInput");
  if (!inp) return;
  inp.value = "Generate choropleth map for above data";
  sendMsg();
}

async function pollSessionState() {
  // Poll session state every 5s to keep badge accurate
  try {
    const res  = await fetch(`${BACKEND}/api/chat/session-state/${sessionId}`);
    const data = await res.json();
    if (data.has_dataframe) {
      updateDatasetBadge({
        rows:       data.dataset_rows,
        columns:    data.dataset_columns,
        geo_scope:  data.geo_scope,
        label:      data.dataset_label,
      });
    } else {
      hideDatasetBadge();
    }
  } catch {}
}

// Start polling when page loads
window.addEventListener("load", () => {
  _badgePollTimer = setInterval(pollSessionState, 5000);
});

// ─────────────────────────────────────────────────────────
// MULTIMODAL FILE UPLOAD
// ─────────────────────────────────────────────────────────
// (multimodal upload handled by unified handleAttachment above)

// ═══════════════════════════════════════════════════════
// SETTINGS MODAL
// ═══════════════════════════════════════════════════════

function openSettings() {
  document.getElementById("settingsModal").style.display = "";
  sttLoadConfig();
  sttLoadStatus();
  sttLoadVoices();
}

function closeSettings() {
  document.getElementById("settingsModal").style.display = "none";
}

async function sttLoadConfig() {
  try {
    const res = await fetch(`${BACKEND}/api/providers/config`);
    const cfg = await res.json();

    // Provider dropdown
    const pSel = document.getElementById("sttProvider");
    if (pSel) pSel.value = cfg.provider || "ollama";
    sttProviderChanged();

    // Ollama model
    await sttLoadOllamaModels();
    const omSel = document.getElementById("sttOllamaModel");
    if (omSel && cfg.ollama_model) omSel.value = cfg.ollama_model;

    // OpenAI model
    const oaSel = document.getElementById("sttOpenaiModel");
    if (oaSel && cfg.openai_model) oaSel.value = cfg.openai_model;

    // Anthropic model
    const anSel = document.getElementById("sttAnthropicModel");
    if (anSel && cfg.anthropic_model) anSel.value = cfg.anthropic_model;

    // Params
    const tempEl = document.getElementById("sttTemp");
    const tokEl  = document.getElementById("sttMaxTok");
    if (tempEl) { tempEl.value = cfg.temperature ?? 0.3; document.getElementById("sttTempVal").textContent = tempEl.value; }
    if (tokEl)  tokEl.value = cfg.max_tokens ?? 2048;

    // Key status
    const infoEl = document.getElementById("sttModelInfo");
    if (infoEl) infoEl.innerHTML = `
      <div class="stt-info-row"><span>Provider</span><b>${cfg.provider || "ollama"}</b></div>
      <div class="stt-info-row"><span>Model</span><b>${cfg.ollama_model || "qwen2.5:7b"}</b></div>
      <div class="stt-info-row"><span>Embedding</span><b>${cfg.embedding_model || "nomic-embed-text"}</b></div>
      <div class="stt-info-row"><span>Temperature</span><b>${cfg.temperature ?? 0.3}</b></div>
      <div class="stt-info-row"><span>Max Tokens</span><b>${cfg.max_tokens ?? 2048}</b></div>
      <div class="stt-info-row"><span>OpenAI Key</span><b>${cfg.openai_key_set ? "✅ Set" : "❌ Not set"}</b></div>
      <div class="stt-info-row"><span>Anthropic Key</span><b>${cfg.anthropic_key_set ? "✅ Set" : "❌ Not set"}</b></div>`;
  } catch(e) {
    const infoEl = document.getElementById("sttModelInfo");
    if (infoEl) infoEl.textContent = "Failed to load config: " + e.message;
  }
}

function sttProviderChanged() {
  const p = document.getElementById("sttProvider")?.value;
  document.getElementById("sttOllamaSection").style.display   = (p==="ollama")    ? "" : "none";
  document.getElementById("sttOpenaiSection").style.display   = (p==="openai")    ? "" : "none";
  document.getElementById("sttAnthropicSection").style.display= (p==="anthropic") ? "" : "none";
}

async function sttLoadOllamaModels() {
  try {
    const res    = await fetch(`${BACKEND}/api/providers/ollama`);
    const models = await res.json();
    const sel    = document.getElementById("sttOllamaModel");
    if (!sel) return;
    sel.innerHTML = models.length
      ? models.map(m => `<option value="${m}">${m}</option>`).join("")
      : `<option value="qwen2.5:7b">qwen2.5:7b</option>`;
  } catch(e) {
    const sel = document.getElementById("sttOllamaModel");
    if (sel) sel.innerHTML = `<option value="qwen2.5:7b">qwen2.5:7b (offline)</option>`;
  }
}

async function sttSaveKey(provider) {
  const keyEl = document.getElementById(provider === "openai" ? "sttOpenaiKey" : "sttAnthropicKey");
  const key   = keyEl?.value?.trim();
  if (!key) { toast("Please enter an API key"); return; }
  try {
    await fetch(`${BACKEND}/api/providers/keys`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({[provider]: key})
    });
    keyEl.value = "";
    const statusEl = document.getElementById(provider === "openai" ? "sttOpenaiStatus" : "sttAnthropicStatus");
    if (statusEl) { statusEl.textContent = "✅ Key saved"; statusEl.style.color = "var(--accent)"; }
    toast(`${provider} API key saved`);
    sttLoadConfig();
  } catch(e) { toast("Failed to save key: " + e.message); }
}

async function sttApply() {
  const provider = document.getElementById("sttProvider")?.value;
  const body = {
    provider,
    temperature: parseFloat(document.getElementById("sttTemp")?.value || 0.3),
    max_tokens:  parseInt(document.getElementById("sttMaxTok")?.value || 2048),
  };
  if (provider === "ollama")    body.ollama_model    = document.getElementById("sttOllamaModel")?.value;
  if (provider === "openai")    body.openai_model    = document.getElementById("sttOpenaiModel")?.value;
  if (provider === "anthropic") body.anthropic_model = document.getElementById("sttAnthropicModel")?.value;
  try {
    await fetch(`${BACKEND}/api/providers/config`, {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)
    });
    toast("Settings applied ✅");
    sttLoadConfig();
  } catch(e) { toast("Failed to apply: " + e.message); }
}

async function sttLoadStatus() {
  const el = document.getElementById("sttStatusGrid");
  if (!el) return;
  try {
    const res  = await fetch(`${BACKEND}/api/providers/status`);
    const data = await res.json();
    const badge = (s, ok) => `<span class="stt-badge ${ok?'ok':'err'}">${s}</span>`;
    el.innerHTML = `
      <div class="stt-info-row"><span>🦙 Ollama</span>${badge(data.ollama, data.ollama==="running")}</div>
      <div class="stt-info-row"><span>🤖 OpenAI</span>${badge(data.openai, data.openai==="connected")}</div>
      <div class="stt-info-row"><span>🔮 Anthropic</span>${badge(data.anthropic, data.anthropic==="connected")}</div>`;
  } catch {
    el.textContent = "Could not reach backend";
  }
}

function sttLoadVoices() {
  const sel = document.getElementById("sttVoice");
  if (!sel || !window.speechSynthesis) return;
  const load = () => {
    const voices = speechSynthesis.getVoices();
    sel.innerHTML = voices.map((v,i) => `<option value="${i}">${v.name} (${v.lang})</option>`).join("");
  };
  speechSynthesis.onvoiceschanged = load;
  load();
}

// ═══════════════════════════════════════════════════════
// MICROPHONE — SPEECH TO TEXT
// ═══════════════════════════════════════════════════════

let micRecognition = null;
let micActive      = false;

function toggleMic() {
  if (micActive) { stopMic(); return; }
  startMic();
}

function startMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast("Speech recognition not supported in this browser. Use Chrome."); return; }
  micRecognition = new SR();
  micRecognition.lang           = "en-US";
  micRecognition.interimResults = true;
  micRecognition.maxAlternatives = 1;

  const btn  = document.getElementById("micBtn");
  const icon = document.getElementById("micIcon");
  if (btn) btn.classList.add("mic-active");
  micActive = true;
  toast("🎙️ Listening…");

  let finalTranscript = "";
  micRecognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalTranscript += t + " ";
      else interim = t;
    }
    const inp = document.getElementById("msgInput");
    if (inp) inp.value = (finalTranscript + interim).trim();
  };

  micRecognition.onend = () => {
    micActive = false;
    if (btn) btn.classList.remove("mic-active");
    const inp = document.getElementById("msgInput");
    if (inp && inp.value.trim()) toast("✅ Voice captured — press Send");
  };

  micRecognition.onerror = (e) => {
    micActive = false;
    if (btn) btn.classList.remove("mic-active");
    toast("Mic error: " + e.error);
  };

  micRecognition.start();
}

function stopMic() {
  if (micRecognition) { micRecognition.stop(); micRecognition = null; }
  micActive = false;
  const btn = document.getElementById("micBtn");
  if (btn) btn.classList.remove("mic-active");
}

// ═══════════════════════════════════════════════════════
// VOICE MODE — CONTINUOUS CONVERSATION
// ═══════════════════════════════════════════════════════

let voiceModeActive = false;
let voiceModeRec    = null;
let voiceMuted      = false;
let voiceAutoSend   = false;

function toggleVoiceMode() {
  if (voiceModeActive) { stopVoiceMode(); return; }
  startVoiceMode();
}

function startVoiceMode() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast("Voice mode requires Chrome browser."); return; }
  voiceModeActive = true;
  document.getElementById("voiceModeOverlay").style.display = "";
  document.getElementById("voiceModeBtn").classList.add("vm-active");
  _vmListen();
}

function stopVoiceMode() {
  voiceModeActive = false;
  if (voiceModeRec) { voiceModeRec.stop(); voiceModeRec = null; }
  document.getElementById("voiceModeOverlay").style.display = "none";
  document.getElementById("voiceModeBtn").classList.remove("vm-active");
  if (window.speechSynthesis) speechSynthesis.cancel();
}

function vmToggleMute() {
  voiceMuted = !voiceMuted;
  const btn = document.getElementById("vmMuteBtn");
  if (btn) btn.textContent = voiceMuted ? "🔊 Unmute" : "🔇 Mute";
  if (voiceMuted && window.speechSynthesis) speechSynthesis.cancel();
}

function _vmListen() {
  if (!voiceModeActive) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  voiceModeRec = new SR();
  voiceModeRec.lang           = "en-US";
  voiceModeRec.interimResults = true;

  const statusEl    = document.getElementById("vmStatus");
  const transcriptEl= document.getElementById("vmTranscript");
  const orb         = document.getElementById("vmOrb");
  if (statusEl) statusEl.textContent = "🎙️ Listening…";
  if (orb) orb.classList.add("listening");

  let finalText = "";
  voiceModeRec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t + " ";
      else interim = t;
    }
    if (transcriptEl) transcriptEl.textContent = (finalText + interim).trim();
  };

  voiceModeRec.onend = async () => {
    if (orb) orb.classList.remove("listening");
    const text = finalText.trim();
    if (text && voiceModeActive) {
      if (statusEl) statusEl.textContent = "🤔 Processing…";
      const inp = document.getElementById("msgInput");
      if (inp) inp.value = text;
      // Send and wait for response
      const reply = await _vmSendAndGetReply(text);
      if (reply && !voiceMuted) {
        _vmSpeak(reply, () => { if (voiceModeActive) setTimeout(_vmListen, 500); });
      } else if (voiceModeActive) {
        setTimeout(_vmListen, 500);
      }
    } else if (voiceModeActive) {
      setTimeout(_vmListen, 300);
    }
  };

  voiceModeRec.onerror = () => {
    if (voiceModeActive) setTimeout(_vmListen, 500);
  };

  voiceModeRec.start();
}

async function _vmSendAndGetReply(text) {
  try {
    const statusEl = document.getElementById("vmStatus");
    const res  = await fetch(`${BACKEND}/api/chat/send`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        message: text, session_id: sessionId,
        session_name: sessionName, colormap: selectedCmap,
        project_id: currentProjId || null,
      }),
      signal: AbortSignal.timeout(60000),
    });
    const data = await res.json();
    if (statusEl) statusEl.textContent = "🔊 Speaking…";
    if (data.reply) {
      appendMsg("assistant", data.reply);
    } else if (data.map_url) {
      appendMsgWithMap("", data.map_url, data.map_id);
    }
    loadChatList();
    return data.reply || "";
  } catch {
    return "";
  }
}

function _vmSpeak(text, onDone) {
  if (!window.speechSynthesis || voiceMuted) { if (onDone) onDone(); return; }
  speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text.replace(/[#*_`]/g, "").slice(0, 800));
  const voices = speechSynthesis.getVoices();
  const vIdx   = parseInt(document.getElementById("sttVoice")?.value || 0);
  if (voices[vIdx]) utter.voice = voices[vIdx];
  utter.rate  = parseFloat(document.getElementById("sttSpeechRate")?.value || 1);
  utter.pitch = parseFloat(document.getElementById("sttSpeechPitch")?.value || 1);
  utter.onend = onDone;
  speechSynthesis.speak(utter);
}

// Auto-speak new AI replies if enabled
const _origAppendMsg = typeof appendMsg === "function" ? appendMsg : null;

// ═══════════════════════════════════════════════════════
// SETTINGS — CARD-STYLE MODEL SELECTORS + ENTER KEY
// ═══════════════════════════════════════════════════════

let _sttSelectedOllamaModel   = "";
let _sttSelectedOpenaiModel   = "gpt-4o";
let _sttSelectedAnthropicModel= "claude-sonnet-4-6";

// Override sttLoadOllamaModels to build card rows
async function sttLoadOllamaModels() {
  const container = document.getElementById("sttOllamaModelCards");
  if (!container) return;
  container.innerHTML = `<div style="color:var(--muted);font-size:12px">Loading…</div>`;
  try {
    const res    = await fetch(`${BACKEND}/api/providers/ollama`);
    const models = await res.json();
    if (!models.length) {
      container.innerHTML = `<div style="color:var(--muted);font-size:12px">No Ollama models found. Run: ollama pull qwen2.5:7b</div>`;
      return;
    }
    container.innerHTML = models.map(m => `
      <div class="stt-mcard" data-m="${m}" onclick="sttSelectOllamaModel('${m}',this)">${m}</div>
    `).join("");
    // Auto-select current
    const first = container.querySelector(`[data-m="${_sttSelectedOllamaModel}"]`) || container.firstElementChild;
    if (first) { first.classList.add("active"); _sttSelectedOllamaModel = first.dataset.m; }
  } catch {
    container.innerHTML = `<div style="color:var(--muted);font-size:12px">Could not reach Ollama</div>`;
  }
}

function sttSelectOllamaModel(model, el) {
  _sttSelectedOllamaModel = model;
  document.querySelectorAll("#sttOllamaModelCards .stt-mcard").forEach(c => c.classList.remove("active"));
  if (el) el.classList.add("active");
}
function sttSelectOAModel(model, el) {
  _sttSelectedOpenaiModel = model;
  document.querySelectorAll("#sttOpenaiSection .stt-mcard").forEach(c => c.classList.remove("active"));
  if (el) el.classList.add("active");
}
function sttSelectANModel(model, el) {
  _sttSelectedAnthropicModel = model;
  document.querySelectorAll("#sttAnthropicSection .stt-mcard").forEach(c => c.classList.remove("active"));
  if (el) el.classList.add("active");
}

// Override sttApply to use card selections + auto-close
async function sttApply() {
  const provider = document.querySelector('input[name="sttProviderRadio"]:checked')?.value || "ollama";
  const body = {
    provider,
    temperature: parseFloat(document.getElementById("sttTemp")?.value || 0.3),
    max_tokens:  parseInt(document.getElementById("sttMaxTok")?.value  || 2048),
  };
  if (provider === "ollama")    body.ollama_model    = _sttSelectedOllamaModel    || "qwen2.5:7b";
  if (provider === "openai")    body.openai_model    = _sttSelectedOpenaiModel    || "gpt-4o";
  if (provider === "anthropic") body.anthropic_model = _sttSelectedAnthropicModel || "claude-sonnet-4-6";

  try {
    await fetch(`${BACKEND}/api/providers/config`, {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)
    });
    const modelName = body.ollama_model || body.openai_model || body.anthropic_model;
    toast(`✅ Switched to ${provider} — ${modelName}`);
    sttLoadConfig();
    // Auto-close after apply
    setTimeout(closeSettings, 800);
  } catch(e) { toast("Failed to apply: " + e.message); }
}

// Override openSettings to load card state
const _origOpenSettings = window.openSettings;
window.openSettings = function() {
  document.getElementById("settingsModal").style.display = "";
  sttLoadConfig();
  sttLoadStatus();
  sttLoadVoiceCards();
  // Enter key in modal = apply
  const modal = document.getElementById("settingsModal");
  modal.onkeydown = (e) => {
    if (e.key === "Enter" && e.target.tagName !== "INPUT") {
      sttApply();
    }
  };
  modal.setAttribute("tabindex","-1");
  modal.focus();
};

async function sttLoadConfig() {
  try {
    const res = await fetch(`${BACKEND}/api/providers/config`);
    const cfg = await res.json();

    // Set radio
    const radio = document.querySelector(`input[name="sttProviderRadio"][value="${cfg.provider||'ollama'}"]`);
    if (radio) { radio.checked = true; sttProviderChanged(); }

    _sttSelectedOllamaModel    = cfg.ollama_model    || "qwen2.5:7b";
    _sttSelectedOpenaiModel    = cfg.openai_model    || "gpt-4o";
    _sttSelectedAnthropicModel = cfg.anthropic_model || "claude-sonnet-4-6";

    await sttLoadOllamaModels();

    // Highlight OpenAI model card
    document.querySelectorAll("#sttOpenaiSection .stt-mcard").forEach(c => {
      c.classList.toggle("active", c.dataset.m === _sttSelectedOpenaiModel);
    });
    // Highlight Anthropic model card
    document.querySelectorAll("#sttAnthropicSection .stt-mcard").forEach(c => {
      c.classList.toggle("active", c.dataset.m === _sttSelectedAnthropicModel);
    });

    // Params
    const tEl = document.getElementById("sttTemp");
    const kEl = document.getElementById("sttMaxTok");
    if (tEl) { tEl.value = cfg.temperature ?? 0.3; document.getElementById("sttTempVal").textContent = tEl.value; }
    if (kEl)  kEl.value = cfg.max_tokens ?? 2048;

    // Info panel
    const info = document.getElementById("sttModelInfo");
    if (info) info.innerHTML = `
      <div class="stt-info-row"><span>Active Provider</span><b>${cfg.provider||"ollama"}</b></div>
      <div class="stt-info-row"><span>Active Model</span><b>${_sttSelectedOllamaModel}</b></div>
      <div class="stt-info-row"><span>Embedding</span><b>${cfg.embedding_model||"nomic-embed-text"}</b></div>
      <div class="stt-info-row"><span>Temperature</span><b>${cfg.temperature??0.3}</b></div>
      <div class="stt-info-row"><span>Max Tokens</span><b>${cfg.max_tokens??2048}</b></div>
      <div class="stt-info-row"><span>OpenAI Key</span><b>${cfg.openai_key_set?"✅ Set":"❌ Not set"}</b></div>
      <div class="stt-info-row"><span>Anthropic Key</span><b>${cfg.anthropic_key_set?"✅ Set":"❌ Not set"}</b></div>`;
  } catch(e) { console.error("sttLoadConfig:", e); }
}

// ═══════════════════════════════════════════════════════
// VOICE CARDS — rich voice options
// ═══════════════════════════════════════════════════════

const VOICE_PRESETS = [
  { label:"🎙️ Natural",   rate:1.0, pitch:1.0,  gender:"female" },
  { label:"👨 Deep Male", rate:0.9, pitch:0.7,  gender:"male"   },
  { label:"👩 Bright",    rate:1.1, pitch:1.3,  gender:"female" },
  { label:"🤖 Robot",     rate:0.8, pitch:0.5,  gender:"any"    },
  { label:"⚡ Fast",      rate:1.6, pitch:1.0,  gender:"any"    },
  { label:"🧓 Calm",      rate:0.8, pitch:0.9,  gender:"male"   },
  { label:"🎓 Clear",     rate:1.0, pitch:1.1,  gender:"female" },
  { label:"🌊 Smooth",    rate:0.95,pitch:0.85, gender:"male"   },
];

let _activeVoicePreset = 0;
let _cachedVoices = [];

function sttLoadVoiceCards() {
  const container = document.getElementById("sttVoiceCards");
  if (!container) return;
  _cachedVoices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  if (!_cachedVoices.length && window.speechSynthesis) {
    speechSynthesis.onvoiceschanged = () => { _cachedVoices = speechSynthesis.getVoices(); };
  }
  container.innerHTML = VOICE_PRESETS.map((p,i) => `
    <div class="stt-vcard${i===_activeVoicePreset?' active':''}" onclick="sttPickVoice(${i},this)">${p.label}</div>
  `).join("");
}

function sttSelectVoiceCard(el) {
  document.querySelectorAll(".stt-vcard").forEach(c=>c.classList.remove("active"));
  el.classList.add("active");
}

function sttPickVoice(idx, el) {
  _activeVoicePreset = idx;
  sttSelectVoiceCard(el);
  const p = VOICE_PRESETS[idx];
  const rateEl  = document.getElementById("sttSpeechRate");
  const pitchEl = document.getElementById("sttSpeechPitch");
  if (rateEl)  { rateEl.value  = p.rate;  document.getElementById("sttRateVal").textContent  = p.rate+"x"; }
  if (pitchEl) { pitchEl.value = p.pitch; document.getElementById("sttPitchVal").textContent = p.pitch; }
}

function sttTestVoice() {
  if (!window.speechSynthesis) { toast("Speech synthesis not supported"); return; }
  speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance("Hello! This is Atlas AI speaking. How can I help you today?");
  _applyVoiceSettings(utter);
  speechSynthesis.speak(utter);
}

function _applyVoiceSettings(utter) {
  const p = VOICE_PRESETS[_activeVoicePreset] || VOICE_PRESETS[0];
  utter.rate  = parseFloat(document.getElementById("sttSpeechRate")?.value  || p.rate);
  utter.pitch = parseFloat(document.getElementById("sttSpeechPitch")?.value || p.pitch);
  // Pick voice by gender preference
  if (_cachedVoices.length) {
    let picked = _cachedVoices.find(v =>
      p.gender !== "any" && v.name.toLowerCase().includes(p.gender)
    ) || _cachedVoices[0];
    if (picked) utter.voice = picked;
  }
}

// Override _vmSpeak to use voice settings
window._vmSpeak = function(text, onDone) {
  if (!window.speechSynthesis || voiceMuted) { if (onDone) onDone(); return; }
  speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text.replace(/[#*_`]/g,"").slice(0,800));
  _applyVoiceSettings(utter);
  utter.onend = onDone;
  speechSynthesis.speak(utter);
};

// ═══════════════════════════════════════════════════════
// PERMISSION LAYER — KEYBOARD SHORTCUTS
// Enter = YES, Arrow keys toggle YES/NO
// ═══════════════════════════════════════════════════════

let _permFocused = "yes"; // "yes" or "no"

document.addEventListener("keydown", (e) => {
  // Only active when permission buttons are visible
  const permRow = document.querySelector(".perm-row");
  if (!permRow) return;

  if (e.key === "Enter") {
    e.preventDefault();
    sendPermission(_permFocused);
    _permFocused = "yes"; // reset
    return;
  }
  if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Tab") {
    e.preventDefault();
    _permFocused = _permFocused === "yes" ? "no" : "yes";
    // Visual highlight
    permRow.querySelectorAll(".perm-btn").forEach(btn => {
      btn.classList.toggle("perm-kbd-focus", btn.classList.contains(_permFocused));
    });
  }
});

// ═══════════════════════════════════════════════════════
// DRAG-DROP — FULL CHAT AREA
// ═══════════════════════════════════════════════════════

function handleChatAreaDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
  document.getElementById("chatBody").classList.add("chat-drag-active");
}

function handleChatAreaDragLeave(e) {
  // Only remove if leaving the chatBody entirely
  if (!e.currentTarget.contains(e.relatedTarget)) {
    document.getElementById("chatBody").classList.remove("chat-drag-active");
  }
}

async function handleChatAreaDrop(e) {
  e.preventDefault();
  document.getElementById("chatBody").classList.remove("chat-drag-active");
  const files = e.dataTransfer?.files;
  if (files && files.length > 0) {
    await _uploadFileAsAttachment(files[0]);
    // Focus the input after drop
    const inp = document.getElementById("msgInput");
    if (inp) inp.focus();
    toast(`📎 ${files[0].name} attached — type your message and send`);
  }
}


// ═══════════════════════════════════════════════════════
// SPEAKER BUTTON — READ ALOUD AI MESSAGES
// ═══════════════════════════════════════════════════════

let _speakingBtn = null;
let _speakingUtter = null;

function speakMsg(btn) {
  // Stop any current speech
  if (window.speechSynthesis) speechSynthesis.cancel();

  // If this button was already speaking — stop only
  if (_speakingBtn === btn) {
    _speakingBtn = null;
    _resetSpeakBtn(btn);
    return;
  }

  // Reset previous button
  if (_speakingBtn) _resetSpeakBtn(_speakingBtn);

  const body = btn.closest(".msg-body");
  const textEl = body?.querySelector(".msg-text");
  if (!textEl) return;
  const clone = textEl.cloneNode(true);
  clone.querySelectorAll("button,svg,.map-result-btns,.perm-row,img").forEach(e=>e.remove());
  const text = (clone.innerText || clone.textContent || "").trim();
  if (!text) return;

  _speakingBtn = btn;
  const label = btn.querySelector(".speak-label");
  if (label) label.textContent = "Stop";
  btn.classList.add("speaking");

  const utter = new SpeechSynthesisUtterance(text);
  _applyVoiceSettings(utter);
  utter.onend = utter.onerror = () => {
    _speakingBtn = null;
    _resetSpeakBtn(btn);
  };
  window.speechSynthesis && speechSynthesis.speak(utter);
}

function _resetSpeakBtn(btn) {
  btn.classList.remove("speaking");
  const label = btn.querySelector(".speak-label");
  if (label) label.textContent = "Read";
}

// ═══════════════════════════════════════════════════════
// PERMISSION LAYER — FIXED ENTER KEY
// Enter only fires for permission when dialog is visible.
// Global enter (send message) unaffected.
// ═══════════════════════════════════════════════════════

// Remove the old global keydown listener and replace with targeted one
(function() {
  // Override the keydown added earlier to avoid double-binding
  let _permHandler = null;

  function _attachPermHandler() {
    if (_permHandler) document.removeEventListener("keydown", _permHandler);
    _permHandler = function(e) {
      const permRow = document.querySelector(".perm-row:last-of-type");
      if (!permRow) return; // no active permission dialog — don't intercept

      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        // Send whichever button has kbd focus, default YES
        const focused = permRow.querySelector(".perm-btn.perm-kbd-focus");
        sendPermission(focused?.classList.contains("no") ? "no" : "yes");
        return;
      }
      if (e.key === "ArrowLeft" || e.key === "ArrowRight" || (e.key === "Tab" && !e.shiftKey)) {
        e.preventDefault();
        const yesBtn = permRow.querySelector(".perm-btn.yes");
        const noBtn  = permRow.querySelector(".perm-btn.no");
        const yFocus = yesBtn?.classList.contains("perm-kbd-focus");
        permRow.querySelectorAll(".perm-btn").forEach(b=>b.classList.remove("perm-kbd-focus"));
        if (yFocus) noBtn?.classList.add("perm-kbd-focus");
        else yesBtn?.classList.add("perm-kbd-focus");
      }
    };
    document.addEventListener("keydown", _permHandler, true); // capture phase
  }
  _attachPermHandler();
})();

// ═══════════════════════════════════════════════════════
// STUDY TOOLS — MAXIMIZE VIEW
// ═══════════════════════════════════════════════════════

function openMaximize(contentHtml, title) {
  let overlay = document.getElementById("maximizeOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "maximizeOverlay";
    overlay.className = "max-overlay";
    overlay.innerHTML = `
      <div class="max-panel">
        <div class="max-header">
          <span class="max-title" id="maxTitle"></span>
          <div style="display:flex;gap:8px">
            <button class="max-btn" onclick="copyMaxContent()">⎘ Copy</button>
            <button class="max-btn max-close" onclick="closeMaximize()">✕ Close</button>
          </div>
        </div>
        <div class="max-body" id="maxBody"></div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", e => { if (e.target === overlay) closeMaximize(); });
  }
  document.getElementById("maxTitle").textContent = title || "Result";
  document.getElementById("maxBody").innerHTML    = contentHtml;
  overlay.style.display = "";
}

function closeMaximize() {
  const o = document.getElementById("maximizeOverlay");
  if (o) o.style.display = "none";
}

function copyMaxContent() {
  const body = document.getElementById("maxBody");
  if (!body) return;
  const clone = body.cloneNode(true);
  clone.querySelectorAll("button").forEach(b=>b.remove());
  navigator.clipboard?.writeText(clone.innerText||"").then(()=>toast("Copied!")).catch(()=>toast("Copy failed"));
}

// Patch study result boxes to add maximize button
function _addMaximizeBtns() {
  const resultIds = ["mcqResult","assignResult","explainResult","mcq-result","assign-result"];
  resultIds.forEach(id => {
    const el = document.getElementById(id);
    if (!el || el.dataset.maxPatched) return;
    el.dataset.maxPatched = "1";
    const title = id.includes("mcq") ? "MCQ Questions" :
                  id.includes("assign") ? "Assignment" : "Explanation";
    const btn = document.createElement("button");
    btn.className   = "max-trigger-btn";
    btn.textContent = "⤢ Maximize";
    btn.onclick     = () => openMaximize(el.innerHTML, title);
    el.parentNode?.insertBefore(btn, el);
  });
}
// Run after any content updates
const _origFmt = window.fmt;
setInterval(_addMaximizeBtns, 2000);

// ═══════════════════════════════════════════════════════
// SETTINGS — ANTHROPIC AUTO MODEL FETCH
// ═══════════════════════════════════════════════════════

async function sttSaveKey(provider) {
  const keyEl   = document.getElementById(provider === "openai" ? "sttOpenaiKey" : "sttAnthropicKey");
  const key     = keyEl?.value?.trim();
  if (!key) { toast("Please enter an API key"); return; }

  const statusEl = document.getElementById(provider === "openai" ? "sttOpenaiStatus" : "sttAnthropicStatus");
  if (statusEl) { statusEl.textContent = "⏳ Saving…"; statusEl.style.color = "var(--muted)"; }

  try {
    await fetch(`${BACKEND}/api/providers/keys`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({[provider]: key})
    });
    keyEl.value = "";
    if (statusEl) { statusEl.textContent = "✅ Key saved"; statusEl.style.color = "var(--accent)"; }
    toast(`${provider} API key saved`);

    // Auto-fetch Anthropic models after saving key
    if (provider === "anthropic") {
      await sttFetchAnthropicModels(key);
    }
    sttLoadConfig();
  } catch(e) {
    if (statusEl) { statusEl.textContent = "❌ Failed: " + e.message; statusEl.style.color = "#e74c3c"; }
  }
}

async function sttFetchAnthropicModels(key) {
  const container = document.getElementById("sttAnthropicSection");
  if (!container) return;
  const statusEl  = document.getElementById("sttAnthropicStatus");
  if (statusEl) { statusEl.textContent = "⏳ Fetching models…"; statusEl.style.color = "var(--muted)"; }

  try {
    // Ask backend to fetch Anthropic models
    const res  = await fetch(`${BACKEND}/api/providers/anthropic-models`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({key})
    });
    const data = await res.json();
    if (data.models && data.models.length) {
      // Rebuild model cards dynamically
      const cardList = container.querySelector(".stt-mcard-list");
      if (cardList) {
        cardList.innerHTML = data.models.map(m =>
          `<div class="stt-mcard" data-m="${m.id}" onclick="sttSelectANModel('${m.id}',this)">${m.name||m.id}</div>`
        ).join("");
      }
      if (statusEl) { statusEl.textContent = `✅ ${data.models.length} models found`; statusEl.style.color = "var(--accent)"; }
    } else {
      if (statusEl) { statusEl.textContent = "✅ Key valid — using default models"; statusEl.style.color = "var(--accent)"; }
    }
  } catch {
    if (statusEl) { statusEl.textContent = "✅ Key saved — could not auto-fetch models"; statusEl.style.color = "var(--muted)"; }
  }
}

// ═══════════════════════════════════════════════════════
// MULTILINGUAL VOICE SUPPORT
// Kannada, Tamil, Telugu, English + presets
// ═══════════════════════════════════════════════════════

const VOICE_PRESETS_V2 = [
  { label:"🎙️ English — Natural",   lang:"en-US", rate:1.0, pitch:1.0  },
  { label:"👨 English — Deep",      lang:"en-US", rate:0.9, pitch:0.7  },
  { label:"👩 English — Bright",    lang:"en-GB", rate:1.1, pitch:1.3  },
  { label:"⚡ English — Fast",      lang:"en-US", rate:1.6, pitch:1.0  },
  { label:"🌊 English — Smooth",    lang:"en-AU", rate:0.95,pitch:0.85 },
  { label:"🇮🇳 Kannada",            lang:"kn-IN", rate:1.0, pitch:1.0  },
  { label:"🇮🇳 Tamil",              lang:"ta-IN", rate:1.0, pitch:1.0  },
  { label:"🇮🇳 Telugu",             lang:"te-IN", rate:1.0, pitch:1.0  },
  { label:"🇮🇳 Hindi",              lang:"hi-IN", rate:1.0, pitch:1.0  },
  { label:"🤖 Robot",               lang:"en-US", rate:0.8, pitch:0.5  },
  { label:"🧓 Calm Male",           lang:"en-US", rate:0.85,pitch:0.8  },
  { label:"🎓 Clear & Precise",     lang:"en-US", rate:1.0, pitch:1.1  },
];

// Override old VOICE_PRESETS
window.VOICE_PRESETS = VOICE_PRESETS_V2;

function sttLoadVoiceCards() {
  const container = document.getElementById("sttVoiceCards");
  if (!container) return;
  _cachedVoices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  if (!_cachedVoices.length && window.speechSynthesis) {
    speechSynthesis.onvoiceschanged = () => {
      _cachedVoices = speechSynthesis.getVoices();
      sttLoadVoiceCards();
    };
  }
  container.innerHTML = VOICE_PRESETS_V2.map((p,i) => `
    <div class="stt-vcard${i===_activeVoicePreset?' active':''}"
         onclick="sttPickVoice(${i},this)"
         title="Language: ${p.lang}">${p.label}</div>
  `).join("");
}

function _applyVoiceSettings(utter) {
  const p = VOICE_PRESETS_V2[_activeVoicePreset] || VOICE_PRESETS_V2[0];
  utter.lang  = p.lang;
  utter.rate  = parseFloat(document.getElementById("sttSpeechRate")?.value  || p.rate);
  utter.pitch = parseFloat(document.getElementById("sttSpeechPitch")?.value || p.pitch);
  if (_cachedVoices.length) {
    // Find voice matching language
    const match = _cachedVoices.find(v => v.lang.startsWith(p.lang.split("-")[0]))
                || _cachedVoices.find(v => v.lang === "en-US")
                || _cachedVoices[0];
    if (match) utter.voice = match;
  }
}

function sttTestVoice() {
  if (!window.speechSynthesis) { toast("Speech synthesis not supported"); return; }
  speechSynthesis.cancel();
  const p = VOICE_PRESETS_V2[_activeVoicePreset] || VOICE_PRESETS_V2[0];
  const samples = {
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು ಅಟ್ಲಾಸ್ AI. ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    "ta-IN": "வணக்கம்! நான் Atlas AI. நான் உங்களுக்கு உதவ தயாராக இருக்கிறேன்.",
    "te-IN": "నమస్కారం! నేను Atlas AI. నేను మీకు సహాయం చేయగలను.",
    "hi-IN": "नमस्ते! मैं Atlas AI हूँ। मैं आपकी सहायता कर सकता हूँ।",
  };
  const text = samples[p.lang] || "Hello! This is Atlas AI speaking. How can I help you today?";
  const utter = new SpeechSynthesisUtterance(text);
  _applyVoiceSettings(utter);
  speechSynthesis.speak(utter);
  toast(`Testing: ${p.label}`);
}


// ═══════════════════════════════════════════════════════
// VOICE PREFERENCE PERSISTENCE
// Saves selected voice, rate, pitch to localStorage
// Restored on page load
// ═══════════════════════════════════════════════════════

const VOICE_PREF_KEY = "atlasai_voice_prefs";

function _saveVoicePrefs() {
  const prefs = {
    presetIdx:  _activeVoicePreset,
    rate:       document.getElementById("sttSpeechRate")?.value  || "1",
    pitch:      document.getElementById("sttSpeechPitch")?.value || "1",
    autoSpeak:  document.getElementById("sttAutoSpeak")?.checked || false,
  };
  try { localStorage.setItem(VOICE_PREF_KEY, JSON.stringify(prefs)); } catch {}
}

function _loadVoicePrefs() {
  try {
    const raw = localStorage.getItem(VOICE_PREF_KEY);
    if (!raw) return;
    const prefs = JSON.parse(raw);
    if (typeof prefs.presetIdx === "number") _activeVoicePreset = prefs.presetIdx;
    const rateEl  = document.getElementById("sttSpeechRate");
    const pitchEl = document.getElementById("sttSpeechPitch");
    const autoEl  = document.getElementById("sttAutoSpeak");
    if (rateEl  && prefs.rate)      { rateEl.value  = prefs.rate;  document.getElementById("sttRateVal")?.setText?.(prefs.rate+"x");  }
    if (pitchEl && prefs.pitch)     { pitchEl.value = prefs.pitch; document.getElementById("sttPitchVal")?.setText?.(prefs.pitch); }
    if (autoEl  && prefs.autoSpeak) autoEl.checked = prefs.autoSpeak;
  } catch {}
}

// Override sttPickVoice to also save
const _origPickVoice = window.sttPickVoice;
window.sttPickVoice = function(idx, el) {
  if (_origPickVoice) _origPickVoice(idx, el);
  _saveVoicePrefs();
};

// Override sttApply to save voice prefs
const _origApply = window.sttApply;
window.sttApply = async function() {
  _saveVoicePrefs();
  if (_origApply) await _origApply();
};

// Auto-speak AI replies if setting is on
const _origAppendMsgForSpeak = window.appendMsg;
window.appendMsg = function(role, text) {
  if (_origAppendMsgForSpeak) _origAppendMsgForSpeak(role, text);
  if (role === "assistant" && text && !text.startsWith("__MAP__")) {
    try {
      const autoEl = document.getElementById("sttAutoSpeak");
      if (autoEl?.checked && window.speechSynthesis && !voiceMuted) {
        const utter = new SpeechSynthesisUtterance(text.replace(/[#*_`]/g,"").slice(0,600));
        _applyVoiceSettings(utter);
        speechSynthesis.speak(utter);
      }
    } catch {}
  }
};

// Load voice prefs on startup
window.addEventListener("load", () => {
  _loadVoicePrefs();
});


// ═══════════════════════════════════════════════════════════════
// ATLAS BRAIN CONTROL CENTER
// BrainManager · ProviderManager · ModelManager · VoiceManager
// ConnectionManager · BrainRegistry · ModelRegistry · VoiceRegistry
// ═══════════════════════════════════════════════════════════════

// ── Registries ───────────────────────────────────────────────
const BrainRegistry = {
  provider: "ollama", model: "qwen2.5:7b",
  mode: "Local", status: "unknown", lastUpdated: null,
  save() { try { localStorage.setItem("atlas_brain", JSON.stringify(this)); } catch{} },
  load() {
    try {
      const d = JSON.parse(localStorage.getItem("atlas_brain")||"{}");
      Object.assign(this, d);
    } catch{}
  }
};

const ModelRegistry = {
  anthropic: [], ollama: [], ollamaCloud: [],
  recent: [],
  addRecent(provider, model) {
    this.recent = this.recent.filter(r => !(r.provider===provider && r.model===model));
    this.recent.unshift({ provider, model, ts: Date.now() });
    this.recent = this.recent.slice(0, 8);
    try { localStorage.setItem("atlas_model_recent", JSON.stringify(this.recent)); } catch{}
  },
  loadRecent() {
    try { this.recent = JSON.parse(localStorage.getItem("atlas_model_recent")||"[]"); } catch{}
  }
};

const VoiceRegistry = {
  selected: 0,
  favorites: [],
  rate: 1, pitch: 1, autoSpeak: false,
  save() {
    try { localStorage.setItem("atlas_voice_reg", JSON.stringify({
      selected: this.selected, favorites: this.favorites,
      rate: this.rate, pitch: this.pitch, autoSpeak: this.autoSpeak
    })); } catch{}
  },
  load() {
    try {
      const d = JSON.parse(localStorage.getItem("atlas_voice_reg")||"{}");
      if (d.selected !== undefined) this.selected = d.selected;
      if (d.favorites) this.favorites = d.favorites;
      if (d.rate)  this.rate  = d.rate;
      if (d.pitch) this.pitch = d.pitch;
      if (d.autoSpeak !== undefined) this.autoSpeak = d.autoSpeak;
    } catch{}
  }
};

// ── Voice Catalog (multilingual) ─────────────────────────────
const VOICE_CATALOG = [
  { name:"Natural",      lang:"en-US", accent:"American",   gender:"F", emoji:"🎙️" },
  { name:"Deep Male",    lang:"en-US", accent:"American",   gender:"M", emoji:"👨" },
  { name:"Bright",       lang:"en-GB", accent:"British",    gender:"F", emoji:"👩" },
  { name:"Australian",   lang:"en-AU", accent:"Australian", gender:"F", emoji:"🦘" },
  { name:"Fast Talker",  lang:"en-US", accent:"American",   gender:"M", emoji:"⚡" },
  { name:"Calm & Slow",  lang:"en-US", accent:"American",   gender:"M", emoji:"🧓" },
  { name:"Clear & Pro",  lang:"en-US", accent:"American",   gender:"F", emoji:"🎓" },
  { name:"Robot",        lang:"en-US", accent:"Synthetic",  gender:"N", emoji:"🤖" },
  { name:"Kannada",      lang:"kn-IN", accent:"Karnataka",  gender:"F", emoji:"🇮🇳" },
  { name:"Tamil",        lang:"ta-IN", accent:"Tamil Nadu", gender:"F", emoji:"🇮🇳" },
  { name:"Telugu",       lang:"te-IN", accent:"Andhra",     gender:"F", emoji:"🇮🇳" },
  { name:"Hindi",        lang:"hi-IN", accent:"Delhi",      gender:"F", emoji:"🇮🇳" },
  { name:"Smooth Jazz",  lang:"en-US", accent:"American",   gender:"M", emoji:"🌊" },
  { name:"Storyteller",  lang:"en-GB", accent:"British",    gender:"M", emoji:"📖" },
];
const VOICE_RATE_MAP  = [1.0,0.9,1.1,1.05,1.6,0.8,1.0,0.8,1.0,1.0,1.0,1.0,0.95,0.9];
const VOICE_PITCH_MAP = [1.0,0.7,1.3,1.1, 1.0,0.9,1.1,0.5,1.0,1.0,1.0,1.0,0.85,0.8];

// ── BrainManager ─────────────────────────────────────────────
const BrainManager = {
  async init() {
    BrainRegistry.load();
    ModelRegistry.loadRecent();
    VoiceRegistry.load();
  },
  async switchBrain(provider, model) {
    const body = { provider };
    if (provider === "ollama")    body.ollama_model    = model;
    if (provider === "openai")    body.openai_model    = model;
    if (provider === "anthropic") body.anthropic_model = model;
    await fetch(`${BACKEND}/api/providers/config`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
    });
    BrainRegistry.provider = provider;
    BrainRegistry.model    = model;
    BrainRegistry.mode     = provider === "ollama" ? "Local" : "Cloud";
    BrainRegistry.lastUpdated = new Date().toISOString();
    BrainRegistry.save();
    ModelRegistry.addRecent(provider, model);
    bccUpdateCurrentCard();
    toast(`🧠 Switched to ${model}`);
  }
};

// ── ProviderManager ───────────────────────────────────────────
const ProviderManager = {
  async discoverOllama() {
    try {
      const r = await fetch(`${BACKEND}/api/providers/ollama`);
      ModelRegistry.ollama = await r.json();
    } catch { ModelRegistry.ollama = []; }
    return ModelRegistry.ollama;
  },
  async discoverAnthropic() {
    const key = document.getElementById("anthrKey")?.value?.trim();
    if (!key) return [];
    try {
      const r = await fetch(`${BACKEND}/api/providers/anthropic-models`, {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({key})
      });
      const d = await r.json();
      ModelRegistry.anthropic = d.models || [];
    } catch { ModelRegistry.anthropic = []; }
    return ModelRegistry.anthropic;
  },
  async getStatus() {
    try {
      const r = await fetch(`${BACKEND}/api/providers/status`);
      return r.json();
    } catch { return { ollama:"stopped", anthropic:"no_key", openai:"no_key" }; }
  },
  async saveKey(provider, key) {
    await fetch(`${BACKEND}/api/providers/keys`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({[provider]: key})
    });
  }
};

// ── VoiceManager ──────────────────────────────────────────────
const VoiceManager = {
  _voices: [],
  _utter:  null,
  init() {
    if (!window.speechSynthesis) return;
    const load = () => { this._voices = speechSynthesis.getVoices(); };
    speechSynthesis.onvoiceschanged = load;
    load();
  },
  _buildUtter(text, preset) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang  = VOICE_CATALOG[preset]?.lang  || "en-US";
    u.rate  = parseFloat(document.getElementById("bccVoiceRate")?.value  || VoiceRegistry.rate  || VOICE_RATE_MAP[preset]  || 1);
    u.pitch = parseFloat(document.getElementById("bccVoicePitch")?.value || VoiceRegistry.pitch || VOICE_PITCH_MAP[preset] || 1);
    const lang = VOICE_CATALOG[preset]?.lang || "en-US";
    const match = this._voices.find(v => v.lang.startsWith(lang.split("-")[0]))
                || this._voices.find(v => v.lang === "en-US")
                || this._voices[0];
    if (match) u.voice = match;
    return u;
  },
  speak(text, onDone) {
    if (!window.speechSynthesis) { if (onDone) onDone(); return; }
    speechSynthesis.cancel();
    const u = this._buildUtter(text.replace(/[#*_`>]/g,"").slice(0,800), VoiceRegistry.selected);
    if (onDone) u.onend = u.onerror = onDone;
    speechSynthesis.speak(u);
  },
  preview(presetIdx) {
    if (!window.speechSynthesis) { toast("Speech not supported in this browser"); return; }
    speechSynthesis.cancel();
    const v = VOICE_CATALOG[presetIdx];
    const samples = {
      "kn-IN":"ನಮಸ್ಕಾರ! ನಾನು ಅಟ್ಲಾಸ್ AI ಆಗಿದ್ದೇನೆ.",
      "ta-IN":"வணக்கம்! நான் Atlas AI.",
      "te-IN":"నమస్కారం! నేను Atlas AI.",
      "hi-IN":"नमस्ते! मैं Atlas AI हूँ।",
    };
    const text = samples[v?.lang] || `Hello! This is the ${v?.name||"selected"} voice.`;
    const u = this._buildUtter(text, presetIdx);
    speechSynthesis.speak(u);
  },
  stop() { window.speechSynthesis && speechSynthesis.cancel(); }
};

// ── ConnectionManager ─────────────────────────────────────────
const ConnectionManager = {
  async checkAll() {
    const t0 = Date.now();
    const status = await ProviderManager.getStatus();
    const latency = Date.now() - t0;
    return { status, latency };
  }
};

// ═══════════════════════════════════════════════════════════════
// BRAIN CONTROL CENTER — UI FUNCTIONS
// ═══════════════════════════════════════════════════════════════

let _bccOpen = false;

function openBCC() {
  document.getElementById("brainCenter").style.display = "";
  _bccOpen = true;
  BrainManager.init().then(() => {
    bccUpdateCurrentCard();
    bccRefreshOllama();
    bccRefreshConnections();
    bccRenderVoiceGrid();
    bccLoadRecentModels();
    bccRenderBrainGrid();
    bccLoadSavedVoiceSliders();
  });
}

function closeBCC() {
  document.getElementById("brainCenter").style.display = "none";
  _bccOpen = false;
}

// Keep legacy openSettings/closeSettings working
function openSettings()  { openBCC(); }
function closeSettings() { closeBCC(); }

function bccTab(name) {
  document.querySelectorAll(".bcc-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".bcc-navbtn").forEach(b => b.classList.remove("active"));
  const tab = document.getElementById("bcc-"+name);
  if (tab) tab.classList.add("active");
  document.querySelector(`[data-tab="${name}"]`)?.classList.add("active");
}

function bccUpdateCurrentCard() {
  const m = document.getElementById("bccCurModel");
  const p = document.getElementById("bccCurProvider");
  const md= document.getElementById("bccCurMode");
  const s = document.getElementById("bccCurStatus");
  if (m)  m.textContent  = BrainRegistry.model    || "—";
  if (p)  p.textContent  = BrainRegistry.provider  || "—";
  if (md) md.textContent = BrainRegistry.mode      || "—";
  if (s) {
    s.className = "bcc-status-dot " + (BrainRegistry.status === "connected" ? "ok" : "");
    s.title = BrainRegistry.status;
  }
}

async function bccRenderBrainGrid() {
  const grid = document.getElementById("bccBrainGrid");
  if (!grid) return;
  grid.innerHTML = `<div class="bcc-loading">⏳ Scanning…</div>`;
  await ProviderManager.discoverOllama();

  const items = [
    ...ModelRegistry.ollama.map(m => ({ provider:"ollama", model:m, icon:"🦙", mode:"Local" })),
    ...(ModelRegistry.anthropic.length ? ModelRegistry.anthropic.map(m => ({
      provider:"anthropic", model:m.id||m, icon:"🔮", mode:"Cloud"
    })) : [
      { provider:"anthropic", model:"claude-sonnet-4-6", icon:"🔮", mode:"Cloud" },
      { provider:"anthropic", model:"claude-opus-4-6",   icon:"🔮", mode:"Cloud" },
    ])
  ];

  if (!items.length) {
    grid.innerHTML = `<div class="bcc-empty">No models found. Start Ollama or add an Anthropic key.</div>`;
    return;
  }
  grid.innerHTML = items.map(i => `
    <div class="bcc-brain-card ${BrainRegistry.model===i.model?'active':''}"
         onclick="BrainManager.switchBrain('${i.provider}','${i.model}').then(bccRenderBrainGrid)">
      <div class="bcc-bc-icon">${i.icon}</div>
      <div class="bcc-bc-model">${i.model}</div>
      <div class="bcc-bc-meta">${i.mode}</div>
      ${BrainRegistry.model===i.model ? '<div class="bcc-bc-active-badge">● Active</div>' : ''}
    </div>`).join("");
}

function bccLoadRecentModels() {
  const el = document.getElementById("bccRecentList");
  if (!el) return;
  if (!ModelRegistry.recent.length) {
    el.innerHTML = `<div class="bcc-empty">No recent models yet</div>`; return;
  }
  el.innerHTML = ModelRegistry.recent.map(r => `
    <div class="bcc-recent-item" onclick="BrainManager.switchBrain('${r.provider}','${r.model}')">
      <span>${r.provider==='anthropic'?'🔮':'🦙'} ${r.model}</span>
      <span class="bcc-recent-meta">${r.provider}</span>
    </div>`).join("");
}

async function bccApplyBrain() {
  const temp   = document.getElementById("bccTemp")?.value;
  const maxTok = document.getElementById("bccMaxTok")?.value;
  await fetch(`${BACKEND}/api/providers/config`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ temperature: parseFloat(temp||0.3), max_tokens: parseInt(maxTok||2048) })
  });
  toast("✅ Brain parameters saved");
}

// Anthropic workspace
async function bccSaveAnthropicKey() {
  const key    = document.getElementById("anthrKey")?.value?.trim();
  const status = document.getElementById("anthrKeyStatus");
  if (!key) { toast("Paste your Anthropic API key first"); return; }
  if (status) { status.textContent = "⏳ Saving & connecting…"; status.style.color="var(--muted)"; }
  await ProviderManager.saveKey("anthropic", key);
  if (status) { status.textContent = "✅ Key saved. Fetching models…"; status.style.color="var(--accent)"; }
  document.getElementById("anthrKey").value = "";
  await bccFetchAnthropicModels();
}

async function bccFetchAnthropicModels() {
  const status   = document.getElementById("anthrKeyStatus");
  const section  = document.getElementById("anthrModelSection");
  const cards    = document.getElementById("anthrModelCards");
  if (cards) cards.innerHTML = `<div class="bcc-loading">⏳ Discovering models…</div>`;
  try {
    const r = await fetch(`${BACKEND}/api/providers/config`);
    const cfg = await r.json();
    // Use known models + try to auto-fetch
    const models = [
      { id:"claude-opus-4-8",    name:"Claude Opus 4.8" },
      { id:"claude-opus-4-6",    name:"Claude Opus 4.6" },
      { id:"claude-sonnet-4-6",  name:"Claude Sonnet 4.6" },
      { id:"claude-haiku-4-5",   name:"Claude Haiku 4.5" },
    ];
    if (section) section.style.display = "";
    if (cards) cards.innerHTML = models.map(m => `
      <div class="bcc-model-card ${cfg.anthropic_model===m.id?'active':''}"
           onclick="bccSelectAnthropicModel('${m.id}',this)">${m.name}</div>`).join("");
    if (status) { status.textContent = `✅ ${models.length} models available`; status.style.color="var(--accent)"; }
    ModelRegistry.anthropic = models;
    const anthrEl = document.getElementById("anthrStatus");
    if (anthrEl) { anthrEl.textContent="Connected"; anthrEl.className="bcc-conn-badge ok"; }
  } catch(e) {
    if (status) { status.textContent = "❌ " + e.message; status.style.color="#e74c3c"; }
  }
}

let _selectedAnthropicModel = "claude-sonnet-4-6";
function bccSelectAnthropicModel(id, el) {
  _selectedAnthropicModel = id;
  document.querySelectorAll("#anthrModelCards .bcc-model-card").forEach(c=>c.classList.remove("active"));
  if (el) el.classList.add("active");
}

async function bccActivateAnthropic() {
  await BrainManager.switchBrain("anthropic", _selectedAnthropicModel);
  bccRenderBrainGrid();
}

// Ollama workspace
async function bccRefreshOllama() {
  const cards  = document.getElementById("ollamaModelCards");
  const status = document.getElementById("ollamaStatus");
  if (cards) cards.innerHTML = `<div class="bcc-loading">⏳ Scanning local models…</div>`;
  const models = await ProviderManager.discoverOllama();
  if (!models.length) {
    if (cards)  cards.innerHTML = `<div class="bcc-empty">No models found. Run: ollama pull qwen2.5:7b</div>`;
    if (status) { status.textContent="Disconnected"; status.className="bcc-conn-badge err"; }
    return;
  }
  if (status) { status.textContent="Connected"; status.className="bcc-conn-badge ok"; }
  if (cards) cards.innerHTML = models.map(m => `
    <div class="bcc-model-card ${BrainRegistry.model===m?'active':''}"
         onclick="BrainManager.switchBrain('ollama','${m}').then(()=>{bccRefreshOllama();bccRenderBrainGrid();})">
      🦙 ${m} ${BrainRegistry.model===m?'<span class="bcc-active-chip">● Active</span>':''}
    </div>`).join("");
}

// Connections dashboard
async function bccRefreshConnections() {
  const { status, latency } = await ConnectionManager.checkAll();
  const setConn = (id, dotId, detailId, s, name) => {
    const ok  = s === "running" || s === "connected";
    const dot = document.getElementById(dotId);
    const det = document.getElementById(detailId);
    if (dot) { dot.className = "bcc-conn-dot " + (ok?"ok":"err"); }
    if (det) {
      det.innerHTML = `
        <div class="bcc-conn-row"><span>Status</span><b class="${ok?'txt-ok':'txt-err'}">${ok?"✅ Online":"❌ Offline"}</b></div>
        <div class="bcc-conn-row"><span>Latency</span><b>${latency}ms</b></div>
        <div class="bcc-conn-row"><span>Last Check</span><b>${new Date().toLocaleTimeString()}</b></div>`;
    }
  };
  setConn("bccConnAnthr",  "bccDotAnthr",  "bccDetailAnthr",  status.anthropic, "Anthropic");
  setConn("bccConnOllama", "bccDotOllama", "bccDetailOllama", status.ollama,    "Ollama");
  BrainRegistry.status = (status.ollama==="running"||status.anthropic==="connected") ? "connected" : "offline";
  BrainRegistry.save();
  bccUpdateCurrentCard();
}

// Voice Center
function bccRenderVoiceGrid() {
  const grid = document.getElementById("bccVoiceGrid");
  if (!grid) return;
  grid.innerHTML = VOICE_CATALOG.map((v,i) => `
    <div class="bcc-voice-card ${i===VoiceRegistry.selected?'selected':''}" id="bccVCard${i}">
      <div class="bcc-vc-emoji">${v.emoji}</div>
      <div class="bcc-vc-name">${v.name}</div>
      <div class="bcc-vc-meta">${v.lang} · ${v.gender}</div>
      <div class="bcc-vc-accent">${v.accent}</div>
      <div class="bcc-vc-btns">
        <button class="bcc-vc-prev" onclick="VoiceManager.preview(${i});event.stopPropagation()">▶ Preview</button>
        <button class="bcc-vc-sel ${i===VoiceRegistry.selected?'active':''}"
                onclick="bccSelectVoice(${i});event.stopPropagation()">${i===VoiceRegistry.selected?'✓ Selected':'Select'}</button>
        <button class="bcc-vc-fav ${VoiceRegistry.favorites.includes(i)?'fav':''}"
                onclick="bccToggleFav(${i});event.stopPropagation()">♥</button>
      </div>
    </div>`).join("");
  bccUpdateActiveVoiceCard();
}

function bccSelectVoice(idx) {
  VoiceRegistry.selected = idx;
  _activeVoicePreset = idx;  // sync with old system
  VoiceRegistry.save();
  bccRenderVoiceGrid();
  bccUpdateActiveVoiceCard();
  toast(`✅ Voice set to: ${VOICE_CATALOG[idx].name}`);
}

function bccToggleFav(idx) {
  const i = VoiceRegistry.favorites.indexOf(idx);
  if (i>=0) VoiceRegistry.favorites.splice(i,1);
  else VoiceRegistry.favorites.push(idx);
  VoiceRegistry.save();
  bccRenderVoiceGrid();
}

function bccUpdateActiveVoiceCard() {
  const v = VOICE_CATALOG[VoiceRegistry.selected];
  const nameEl = document.getElementById("bccVoiceActiveName");
  const subEl  = document.getElementById("bccVoiceActiveSub");
  if (nameEl) nameEl.textContent = `${v?.emoji||''} ${v?.name||"Default"}`;
  if (subEl)  subEl.textContent  = `${v?.lang||"en-US"} · ${v?.accent||""}`;
}

function bccPreviewCurrentVoice() { VoiceManager.preview(VoiceRegistry.selected); }

function bccStudioPlay() {
  const text = document.getElementById("bccStudioText")?.value?.trim();
  if (!text) { toast("Enter text in the studio"); return; }
  VoiceManager.preview(VoiceRegistry.selected); // use current voice but with studio text
  const u = new SpeechSynthesisUtterance(text);
  speechSynthesis.cancel();
  u.lang  = VOICE_CATALOG[VoiceRegistry.selected]?.lang || "en-US";
  u.rate  = parseFloat(document.getElementById("bccVoiceRate")?.value || 1);
  u.pitch = parseFloat(document.getElementById("bccVoicePitch")?.value || 1);
  speechSynthesis.speak(u);
}

function bccStudioStop() { VoiceManager.stop(); }

function bccSaveVoice() {
  VoiceRegistry.rate      = parseFloat(document.getElementById("bccVoiceRate")?.value || 1);
  VoiceRegistry.pitch     = parseFloat(document.getElementById("bccVoicePitch")?.value || 1);
  VoiceRegistry.autoSpeak = document.getElementById("bccAutoSpeak")?.checked || false;
  VoiceRegistry.save();
  toast("✅ Voice settings saved");
  closeBCC();
}

function bccLoadSavedVoiceSliders() {
  const rateEl  = document.getElementById("bccVoiceRate");
  const pitchEl = document.getElementById("bccVoicePitch");
  const autoEl  = document.getElementById("bccAutoSpeak");
  if (rateEl)  { rateEl.value  = VoiceRegistry.rate||1;  document.getElementById("bccRateVal").textContent=(VoiceRegistry.rate||1)+"×"; }
  if (pitchEl) { pitchEl.value = VoiceRegistry.pitch||1; document.getElementById("bccPitchVal").textContent=VoiceRegistry.pitch||1; }
  if (autoEl)  autoEl.checked  = VoiceRegistry.autoSpeak||false;
}

function bccApplyAdvanced() {
  const ctx    = parseInt(document.getElementById("bccCtxLen")?.value||8192);
  const topP   = parseFloat(document.getElementById("bccTopP")?.value||0.9);
  fetch(`${BACKEND}/api/providers/config`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ context_length:ctx, top_p:topP })
  }).then(()=>toast("✅ Advanced settings saved"));
}

// Auto-speak using VoiceManager (override previous implementation)
window._bccAutoSpeak = function(text) {
  if (VoiceRegistry.autoSpeak && text && !text.startsWith("__MAP__")) {
    VoiceManager.speak(text);
  }
};

// Sync speakMsg to use VoiceManager
window.speakMsg = function(btn) {
  if (!window.speechSynthesis) return;
  if (_speakingBtn === btn) {
    speechSynthesis.cancel(); _speakingBtn = null; _resetSpeakBtn(btn); return;
  }
  if (_speakingBtn) _resetSpeakBtn(_speakingBtn);
  const body  = btn.closest(".msg-body");
  const textEl= body?.querySelector(".msg-text");
  if (!textEl) return;
  const clone = textEl.cloneNode(true);
  clone.querySelectorAll("button,svg,.map-result-btns,.perm-row,img").forEach(e=>e.remove());
  const text  = (clone.innerText||clone.textContent||"").trim();
  if (!text) return;
  _speakingBtn = btn;
  btn.querySelector(".speak-label") && (btn.querySelector(".speak-label").textContent = "Stop");
  btn.classList.add("speaking");
  VoiceManager.speak(text, () => { _speakingBtn=null; _resetSpeakBtn(btn); });
};

// Init on page load
window.addEventListener("load", () => {
  BrainManager.init();
  VoiceManager.init();
});

