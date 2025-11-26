# AI/FeatureImpact/impact_scorer.py
from utils.llm_client import LLMClient
import math

class ImpactScorer:
    """
    Combines heuristic scoring with an LLM-based refinement.
    Heuristic estimates:
     - files_affected_count -> base impact
     - cross-file symbol usage -> risk multiplier
    """

    def __init__(self):
        self.llm = LLMClient()

    def heuristic_score(self, affected_files, symbol_map):
        # base = log(files+1)
        base = math.log(len(affected_files) + 1) * 3.0
        # extra risk if many shared symbols
        shared = 0
        for sym, paths in symbol_map.items():
            if len(paths) > 1:
                shared += 1
        shared_factor = 1.0 + (shared * 0.1)
        score = min(10, base * shared_factor)
        return round(score, 2)

    def llm_refine(self, description, context_snippets):
        """
        Ask LLM to provide a qualitative risk summary and a numeric 1-10 suggestion.
        """
        prompt = f"""
Project change description:
{description}

Context snippets (files/important lines):
{context_snippets}

Return JSON: {{ "risk_score": <1-10 int>, "risk_reason": "<short text>" }}
"""
        try:
            res = self.llm.query("deepseek-v2:16b", prompt)
            # Try to parse JSON-ish result
            import json
            j = json.loads(res)
            return j.get("risk_score", None), j.get("risk_reason", "")
        except Exception:
            return None, ""

    def score(self, description, affected_files, symbol_map, context_snippets):
        h = self.heuristic_score(affected_files, symbol_map)
        llm_score, reason = self.llm_refine(description, context_snippets)
        if llm_score is None:
            final = h
        else:
            # combine: avg
            final = round((h + llm_score) / 2.0, 2)
        return {"final_score": final, "heuristic": h, "llm_reason": reason}
