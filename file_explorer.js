async function loadFileTree() {
    const res = await fetch("http://localhost:5000/file_tree");
    const data = await res.json();

    const cont = document.getElementById("file-tree");
    cont.innerHTML = "";

    data.files.forEach(f => {
        const el = document.createElement("div");
        el.textContent = f;
        el.className = "file-item";
        el.onclick = () => openFile(f);
        cont.appendChild(el);
    });
}

async function openFile(path) {
    const res = await fetch("http://localhost:5000/open_file", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ path })
    });

    const data = await res.json();
    editor.setValue(data.content);
}

loadFileTree();
