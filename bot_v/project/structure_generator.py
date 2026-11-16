from bot_v.llm.client import LLMClient
from bot_v.llm.parsing import extract_json


class StructureGenerator:
    """
    Generates folder-file structure from high-level project idea.
    """

    def __init__(self):
        self.llm = LLMClient()

    def generate_structure(self, description):
        plan = self.llm.query(
            "general",
            f"""
You are an expert software architect.

Create a FULL folder structure for this project:
'{description}'

Return result in pure JSON format like:
{{
  "src": {{
     "index.js": "",
     "utils": {{ "math.js": "" }}
  }},
  "public": {{
     "index.html": ""
  }}
}}
"""
        )

        return extract_json(plan)
