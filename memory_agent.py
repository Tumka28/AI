class MemoryAgent:
    def __init__(self):
        self.logs = []

    def add(self, speaker, text):
        self.logs.append({"speaker": speaker, "text": text})

    def get_context(self, limit=6):
        return self.logs[-limit:]
