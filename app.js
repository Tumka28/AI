// ===========================================================
// AI Unified IDE - CLEAN FINAL VERSION
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
// REALTIME TERMINAL STREAM (SSE)
// ===========================================================
function startStream() {
    const ev = new EventSource("http://localhost:5000/stream");

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
    const res = await fetch("http://localhost:5000/file_tree");
    const data = await res.json();

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
    const res = await fetch("http://localhost:5000/open_file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
    });

    const data = await res.json();
    editor.setValue(data.content);
}


// ===========================================================
// CHAT SYSTEM (GPT-like chat)
// ===========================================================
async function sendChat() {
    const msg = document.getElementById("chat-input").value.trim();
    if (!msg) return;

    addChatMessage("You: " + msg);
    document.getElementById("chat-input").value = "";

    const res = await fetch("http://localhost:5000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
    });

    const data = await res.json();
    addChatMessage("AI: " + data.reply);
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
// AI AGENTS
// ===========================================================

// Multi-Agent 2.0
async function runMultiAgentV2() {
    const goal = prompt("Enter goal for Multi-Agent:");
    if (!goal) return;

    const res = await fetch("http://localhost:5000/multi_agent_v2", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal })
    });

    const data = await res.json();
    editor.setValue(data.code || "// No code generated");
}

// AutoGPT
async function runAutoGPT() {
    const goal = prompt("Enter AutoGPT goal:");
    if (!goal) return;

    const res = await fetch("http://localhost:5000/autogpt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal })
    });

    const data = await res.json();
    editor.setValue(data.final_code || "// No output");
    showTerminal(data);
}

// Auto Task Manager
async function runAutoTask() {
    const goal = prompt("Enter task goal:");
    if (!goal) return;

    const res = await fetch("http://localhost:5000/auto_task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal })
    });

    showTerminal(await res.json());
}

// Project Generator
async function generateProject() {
    const desc = prompt("Project description:");
    if (!desc) return;

    const res = await fetch("http://localhost:5000/generate_project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: desc })
    });

    showTerminal(await res.json());
}

// Semantic Index
async function buildSemanticIndex() {
    const res = await fetch("http://localhost:5000/semantic/build", {
        method: "POST"
    });
    showTerminal(await res.json());
}

async function semanticSearch() {
    const q = prompt("Search query:");
    if (!q) return;

    const res = await fetch("http://localhost:5000/semantic/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q })
    });

    showTerminal(await res.json());
}

// Feature Impact
async function featureImpact() {
    const desc = prompt("Feature change:");
    if (!desc) return;

    const res = await fetch("http://localhost:5000/feature_impact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: desc })
    });

    const data = await res.json();
    showTerminal(data);

    if (data.patch_preview && data.patch_preview.length > 0) {
        editor.setValue(data.patch_preview[0].diff);
    }
}

// Test Generator
async function generateTests() {
    const code = editor.getValue();

    const res = await fetch("http://localhost:5000/generate_tests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
    });

    const data = await res.json();
    showTerminal(data);

    if (data.length > 0) {
        editor.setValue(data[0].content);
    }
}

// Self Optimizer
async function selfOptimize() {
    const code = editor.getValue();

    const res = await fetch("http://localhost:5000/self_optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
    });

    const data = await res.json();
    editor.setValue(data.improved_code);
    showTerminal(data);
}

// Long Memory
async function longMemoryTest() {
    const msg = prompt("Message to store:");
    if (!msg) return;

    const res = await fetch("http://localhost:5000/long_memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: "IDE-Agent", message: msg })
    });

    showTerminal(await res.json());
}


// ===========================================================
// UTILS
// ===========================================================
function showTerminal(d) {
    document.getElementById("terminal").textContent =
        JSON.stringify(d, null, 2);
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

