import re

class SkillExtractor:
    """
    Extracts code patterns that can become independent tools.
    Safe: Only analyzes simple JS/py utility patterns.
    """

    def extract(self, code):
        skills = []

        # 1. Detect Utility Functions
        matches = re.findall(r"function\s+(\w+)\s*\((.*?)\)\s*\{", code)
        for fn_name, params in matches:
            skills.append({
                "type": "function",
                "name": fn_name,
                "params": [p.strip() for p in params.split(",") if p.strip()]
            })

        # 2. Detect patterns like "calculate", "format", "convert"
        if "convert" in code.lower():
            skills.append({
                "type": "pattern",
                "name": "auto_convert",
                "params": []
            })

        return skills
