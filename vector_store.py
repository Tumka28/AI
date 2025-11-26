import numpy as np
import json
import os

STORE_PATH = "AI/LongMemory/memory.json"

class VectorStore:
    """
    Stores memory vectors + text.
    """

    def __init__(self):
        if not os.path.exists(STORE_PATH):
            with open(STORE_PATH, "w") as f:
                json.dump({"items": []}, f, indent=2)

        with open(STORE_PATH, "r") as f:
            self.data = json.load(f)

    def save(self):
        with open(STORE_PATH, "w") as f:
            json.dump(self.data, f, indent=2)

    def add(self, text, vector):
        item = {
            "text": text,
            "vector": vector.tolist()
        }
        self.data["items"].append(item)
        self.save()

    def search(self, query_vec, top_k=5):
        items = self.data["items"]
        if not items:
            return []

        def cos_sim(a, b):
            a = np.array(a); b = np.array(b)
            denom = (np.linalg.norm(a) * np.linalg.norm(b))
            return float(np.dot(a,b) / denom) if denom != 0 else 0

        # compute similarities
        scored = []
        for it in items:
            sim = cos_sim(query_vec, it["vector"])
            scored.append((sim, it["text"]))

        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[:top_k]
