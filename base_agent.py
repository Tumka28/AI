class BaseAgent:
    def __init__(self, name, llm):
        self.name = name
        self.llm = llm
        self.memory = []

    def add_memory(self, text):
        self.memory.append(text)

    def think(self, prompt):
        mem = "\n".join(self.memory[-5:])
        return self.llm.query(
            "deepseek-v2:16b",
            f"[{self.name} agent]\nMemory:\n{mem}\n\nTask:\n{prompt}"
        )
