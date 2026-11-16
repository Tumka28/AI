# bot_v/feature_impact/test_suggester.py
from bot_v.llm.client import LLMClient
import json

class TestSuggester:
    """
    Suggests tests that should be added/updated for a change.
    Returns structured suggestions (file, test_description, priority)
    """

    def __init__(self):
        self.llm = LLMClient()

    def suggest(self, change_description, sample_contexts, top_n=5):
        ctx = "\n\n".join(sample_contexts[:5])
        prompt = f"""
A code change is proposed:
{change_description}

Relevant code snippets:
{ctx}

Suggest up to {top_n} test cases or test-file changes that should be added to ensure safety.
Return JSON list of objects:
[{{"file": "...", "test": "...", "priority": "high|medium|low"}}]
"""
        try:
            res = self.llm.query("general", prompt)
            return json.loads(res)
        except Exception:
            # fallback simple suggestion
            return [{"file": "tests/important_test.py", "test": "basic sanity test", "priority": "high"}]
