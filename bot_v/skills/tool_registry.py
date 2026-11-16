import json
import os

from bot_v.config import data_path

REGISTRY_PATH = str(data_path("skills", "auto_tools.json"))


class ToolRegistry:
    def __init__(self):
        if not os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, "w") as f:
                f.write(json.dumps({"tools": []}, indent=2))

    def load(self):
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)

    def save(self, data):
        with open(REGISTRY_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def add_tool(self, tool_data):
        data = self.load()
        data["tools"].append(tool_data)
        self.save(data)
