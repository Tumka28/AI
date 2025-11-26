from AI.LongMemory.long_memory_controller import LongMemoryController

class KnowledgeRefresher:
    """
    Removes irrelevant memories and strengthens useful ones.
    """

    def __init__(self):
        self.memory = LongMemoryController().memory.mem

    def refresh(self, output):
        # store the optimized insight to memory
        self.memory.remember(f"[Optimized Knowledge]\n{output}")

        return True
