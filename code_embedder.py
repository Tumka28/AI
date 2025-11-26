from utils.llm_client import LLMClient
import numpy as np

class CodeEmbedder:
    """
    Creates embeddings for code and text.
    """

    def __init__(self):
        self.llm = LLMClient()

    def embed(self, text):
        vec = self.llm.embed("deepseek-coder-v2:16b", text)
        return np.array(vec, dtype=float)
