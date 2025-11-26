import json
import numpy as np
from AI.SemanticSearch.code_embedder import CodeEmbedder

INDEX_PATH = "AI/SemanticSearch/index.json"

class SemanticSearch:
    def __init__(self):
        self.embedder = CodeEmbedder()
        self.index = None
        self._load()

    def _load(self):
        try:
            with open(INDEX_PATH, "r") as fh:
                self.index = json.load(fh)
        except:
            self.index = {"files": []}

    def search(self, query, top_k=5):
        query_vec = self.embedder.embed(query)

        def cos(a, b):
            a = np.array(a)
            b = np.array(b)
            denom = (np.linalg.norm(a) * np.linalg.norm(b))
            return float(np.dot(a, b) / denom) if denom else 0

        scored = []
        for f in self.index["files"]:
            sim = cos(query_vec, f["vector"])
            scored.append((sim, f["path"]))

        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[:top_k]
