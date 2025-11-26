from utils.llm_client import LLMClient

class HighLevelQueryExpander:
    """
    Converts natural language queries to more code-oriented search prompts.
    """

    def __init__(self):
        self.llm = LLMClient()

    def expand(self, query):
        return self.llm.query(
            "deepseek-v2:16b",
            f"""
User search query:
{query}

Rewrite this query into a code-search-friendly form.
Return ONLY the rewritten query text.
"""
        ).strip()
