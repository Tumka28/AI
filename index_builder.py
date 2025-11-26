import json
import os
from AI.SemanticSearch.code_embedder import CodeEmbedder

INDEX_PATH = "AI/SemanticSearch/index.json"

class IndexBuilder:
    def __init__(self):
        self.embedder = CodeEmbedder()

    def build(self, files):
        index = {"files": []}

        for f in files:
            vec = self.embedder.embed(f["content"])
            index["files"].append({
                "path": f["path"],
                "vector": vec.tolist()
            })

        with open(INDEX_PATH, "w") as fh:
            json.dump(index, fh, indent=2)

        return True
