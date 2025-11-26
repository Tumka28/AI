from AI.LongMemory.memory_manager import LongMemoryManager

class MemoryIntegration:
    """
    Connects LongMemory with agents and AutoGPT system.
    """

    def __init__(self):
        self.mem = LongMemoryManager()

    def enrich_prompt(self, agent_name, user_input):
        # 1. Fetch relevant memories
        recalled = self.mem.recall(user_input, top_k=3)
        recall_text = "\n".join([f"- {t}" for _, t in recalled])

        # 2. Combine with agent prompt
        system_context = f"""
[LongTermMemory for {agent_name}]
Relevant past experiences:
{recall_text}

User request:
{user_input}
"""
        return system_context

    def store_interaction(self, text):
        self.mem.remember(text)
