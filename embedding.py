from utils.llm_client import LLMClient
import numpy as np

class Embedder:
    """
    Converts text -> vector embedding using LLM backend.
    """

    def __init__(self):
        self.llm = LLMClient()

    def embed(self, text):
        vec = self.llm.embed("deepseek-v2:16b", text)
        return np.array(vec, dtype=float)
