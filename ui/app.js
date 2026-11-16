// ===========================================================
// Bot V IDE
// Served by bot_v/server.py, so every API call is same-origin.
// ===========================================================

let editor;

// ===========================================================
// MONACO EDITOR LOADING
// ===========================================================
require.config({
    paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs" }
});

require(["vs/editor/editor.main"], () => {
    editor = monaco.editor.create(document.getElementById("editor"), {
        value: "// Write code here...",
        language: "javascript",
        theme: "vs-dark",
        automaticLayout: true
    });
});


// ===========================================================
// API HELPERS
// ===========================================================
async function postJSON(url, body) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
    });
    return res.json();
}

async function getJSON(url) {
    const res = await fetch(url);
    return res.json();
}


// ===========================================================
// REALTIME TERMINAL STREAM (SSE)
// ===========================================================
function startStream() {
    const ev = new EventSource("/stream");

    ev.onmessage = (e) => {
        if (e.data) addTerminal(e.data);
    };

    ev.onerror = () => addTerminal("[STREAM ERROR]");
}
startStream();

function addTerminal(text) {
    const term = document.getElementById("terminal");
    term.textContent += text + "\n";
    term.scrollTop = term.scrollHeight;
}


// ===========================================================
// FILE TREE + OPEN FILE
// ===========================================================
async function loadFileTree() {
    const data = await getJSON("/file_tree");

    const pane = document.getElementById("file-tree");
    pane.innerHTML = "";

    data.files.forEach((f) => {
        const el = document.createElement("div");
        el.textContent = f;
        el.className = "file-item";
        el.onclick = () => openFile(f);
        pane.appendChild(el);
    });
}
loadFileTree();

async function openFile(path) {
    const data = await postJSON("/open_file", { path });
    if (data.error) return addTerminal("open_file: " + data.error);
    editor.setValue(data.content);
}

function openFileBrowser() {
    loadFileTree();
}


// ===========================================================
// CHAT (Bot V decides: local model or OpenJarvis)
// ===========================================================
async function sendChat() {
    const input = document.getElementById("chat-input");
    const msg = input.value.trim();
    if (!msg) return;

    const backend = document.getElementById("chat-backend").value;
    addChatMessage("You: " + msg);
    input.value = "";

    const data = await postJSON("/chat", { message: msg, backend });
    if (data.error) return addChatMessage("Error: " + data.error);

    let who = "Bot V";
    if (data.backend === "openjarvis") who = "Bot V → OpenJarvis";
    if (data.fallback_from) who += " (fallback)";
    addChatMessage(who + ": " + data.reply);
}

function addChatMessage(msg) {
    const box = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "chat-msg";
    el.textContent = msg;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
}


// ===========================================================
// OPENJARVIS (controlled by Bot V)
// ===========================================================
async function askOpenJarvis() {
    const task = prompt("Task for OpenJarvis:");
    if (!task) return;
    const agent = prompt("Agent (empty = none, e.g. orchestrator, native_react, deep_research):", "") || null;
    const toolsRaw = prompt("Tools, comma-separated (empty = none, e.g. calculator,web_search):", "") || "";
    const tools = toolsRaw.split(",").map((t) => t.trim()).filter(Boolean);

    addChatMessage(`You → OpenJarvis: ${task}`);
    const data = await postJSON("/openjarvis/ask", { task, agent, tools });
    addChatMessage(`Bot V → OpenJarvis [${data.status}]: ${data.reply}`);
    showTerminal(data);
}

async function openJarvisTools() {
    showTerminal(await getJSON("/openjarvis/tools"));
}

async function openJarvisAgents() {
    showTerminal(await getJSON("/openjarvis/agents"));
}

async function botStatus() {
    showTerminal(await getJSON("/status"));
}

async function experienceLog() {
    showTerminal(await getJSON("/experience?n=20"));
}


// ===========================================================
// BOT V'S OWN AGENTS
// ===========================================================
async function runMultiAgentV2() {
    const goal = prompt("Enter goal for Multi-Agent:");
    if (!goal) return;
    const data = await postJSON("/multi_agent_v2", { goal });
    editor.setValue(data.code || "// No code generated");
    showTerminal(data);
}

async function runAutoGPT() {
    const goal = prompt("Enter AutoGPT goal:");
    if (!goal) return;
    const data = await postJSON("/autogpt", { goal });
    editor.setValue(data.final_code || "// No output");
    showTerminal(data);
}

async function generateProject() {
    const desc = prompt("Project description:");
    if (!desc) return;
    showTerminal(await postJSON("/generate_project", { description: desc }));
}

async function buildSemanticIndex() {
    showTerminal(await postJSON("/semantic/build"));
}

async function semanticSearch() {
    const q = prompt("Search query:");
    if (!q) return;
    showTerminal(await postJSON("/semantic/search", { query: q }));
}

async function selfOptimize() {
    const data = await postJSON("/self_optimize", { code: editor.getValue() });
    if (data.improved_code) editor.setValue(data.improved_code);
    showTerminal(data);
}

async function longMemoryTest() {
    const msg = prompt("Message for long-term memory:");
    if (!msg) return;
    showTerminal(await postJSON("/long_memory", { agent: "IDE-Agent", message: msg }));
}


// ===========================================================
// UTILS
// ===========================================================
function showTerminal(d) {
    document.getElementById("terminal").textContent = JSON.stringify(d, null, 2);
}


// ===========================================================
// BUTTON RIPPLE EFFECT
// ===========================================================
document.addEventListener("click", (e) => {
    if (e.target.tagName === "BUTTON") {
        const btn = e.target;

        const ripple = document.createElement("span");
        ripple.classList.add("ripple");

        const rect = btn.getBoundingClientRect();
        ripple.style.left = e.clientX - rect.left + "px";
        ripple.style.top = e.clientY - rect.top + "px";

        btn.appendChild(ripple);
        setTimeout(() => ripple.remove(), 450);
    }
});

document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("chat-input");
    if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
});
