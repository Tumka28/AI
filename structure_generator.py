from utils.llm_client import LLMClient

class StructureGenerator:
    """
    Generates folder-file structure from high-level project idea.
    """

    def __init__(self):
        self.llm = LLMClient()

    def generate_structure(self, description):
        plan = self.llm.query(
            "deepseek-v2:16b",
            f"""
You are an expert software architect.

Create a FULL folder structure for this project:
'{description}'

Return result in pure JSON format like:
{
  "src": {
     "index.js": "",
     "utils": { "math.js": "" }
  },
  "public": {
     "index.html": ""
  }
}
"""
        )

        # LLM always returns valid JSON for this structured prompt
        import json
        return json.loads(plan)
