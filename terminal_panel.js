function writeTerminal(msg) {
    const term = document.getElementById("terminal");
    term.textContent += "\n" + msg;
    term.scrollTop = term.scrollHeight;
}
