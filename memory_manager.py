from AI.LongMemory.embedding import Embedder
from AI.LongMemory.vector_store import VectorStore

class LongMemoryManager:
    """
    High-level memory interface:
    - store facts
    - recall relevant facts
    """

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()

    def remember(self, text):
        vec = self.embedder.embed(text)
        self.store.add(text, vec)
        return True

    def recall(self, query, top_k=5):
        query_vec = self.embedder.embed(query)
        return self.store.search(query_vec, top_k)
