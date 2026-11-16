from bot_v.llm.client import LLMClient
import numpy as np

class CodeEmbedder:
    """
    Creates embeddings for code and text.
    """

    def __init__(self):
        self.llm = LLMClient()

    def embed(self, text):
        vec = self.llm.embed("embed", text)
        return np.array(vec, dtype=float)
