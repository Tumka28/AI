# AI/FeatureImpact/static_analyzer.py
import re
from collections import defaultdict

class StaticAnalyzer:
    """
    Very lightweight static analysis:
    - Finds function and class definitions (py/js).
    - Finds import/use relationships (very approximate).
    - Builds a simple map: symbol -> files where defined / used.
    """

    def extract_symbols(self, content, path):
        symbols = set()
        # python defs
        for m in re.findall(r"def\s+([a-zA-Z_]\w+)\s*\(", content):
            symbols.add(m)
        for m in re.findall(r"class\s+([A-Z][a-zA-Z0-9_]+)\s*[:\(]", content):
            symbols.add(m)
        # js functions
        for m in re.findall(r"function\s+([a-zA-Z_]\w+)\s*\(", content):
            symbols.add(m)
        # js exports (module.exports / export)
        for m in re.findall(r"export\s+function\s+([a-zA-Z_]\w+)\s*\(", content):
            symbols.add(m)
        # simple const/let assignments of arrow functions
        for m in re.findall(r"(?:const|let|var)\s+([a-zA-Z_]\w+)\s*=\s*\(?.*?\)?\s*=>", content):
            symbols.add(m)

        return list(symbols)

    def find_usages(self, content):
        # find potential symbol uses: word-like tokens
        tokens = re.findall(r"\b([a-zA-Z_]\w+)\b", content)
        # return set to speed up
        return set(tokens)

    def analyze_project(self, files):
        """
        Returns:
        - definitions: symbol -> [paths]
        - usages: path -> set(symbols used)
        """
        definitions = defaultdict(list)
        usages = {}

        for f in files:
            path = f["path"]
            content = f["content"]

            defs = self.extract_symbols(content, path)
            used = self.find_usages(content)

            usages[path] = used
            for s in defs:
                definitions[s].append(path)

        return {"definitions": dict(definitions), "usages": usages}
