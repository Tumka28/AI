from llm_client import LLMClient

class BranchEvaluator:
    """
    Scores Tree-of-Thought branches and selects the strongest one.
    """
    def __init__(self):
        self.llm = LLMClient()

    def evaluate(self, prompt, branches):
        scored = []

        for b in branches:
            score = self.llm.query(
                "deepseek-v2:16b",
                f"""
Evaluate this reasoning for solving the problem:

Problem: {prompt}
Reasoning: {b}

Rate from 1 to 10.
ONLY return the number.
"""
            )

            try:
                score = int(score.strip())
            except:
                score = 1

            scored.append((b, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0]
