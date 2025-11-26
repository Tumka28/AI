import json
import os

SCHEMA_PATH = "AI/SkillExpansion/tools.json"

class SchemaManager:
    """
    Manages JSON schema of auto-generated skills/tools.
    """

    def __init__(self):
        if not os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "w") as f:
                json.dump({"tools": []}, f, indent=2)

    def add_tool(self, name, params, path):
        with open(SCHEMA_PATH, "r") as f:
            data = json.load(f)

        data["tools"].append({
            "name": name,
            "params": params,
            "path": path
        })

        with open(SCHEMA_PATH, "w") as f:
            json.dump(data, f, indent=2)
