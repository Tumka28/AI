// --- Initialize Monaco Editor ---
let editor;

require.config({
    paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs" }
});

require(["vs/editor/editor.main"], function () {
    editor = monaco.editor.create(document.getElementById("editor"), {
        value: "// Start coding...",
        language: "javascript",
        theme: "vs-dark",
        automaticLayout: true
    });
});

// --- AI REQUEST FUNCTION ---
async function sendAI(type) {
    const code = editor.getValue();

    const res = await fetch("http://localhost:5000/ide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, code })
    });

    const data = await res.json();

    document.getElementById("output").textContent = data.output;

    if (data.new_code) {
        editor.setValue(data.new_code);
    }
}
