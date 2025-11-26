import importlib.util
import json
from AI.SkillExpansion.schema_manager import SCHEMA_PATH

class IntegrationUpdater:
    """
    Dynamically loads generated tools into the system tool_map.
    """

    def load_tools(self):
        with open(SCHEMA_PATH, "r") as f:
            data = json.load(f)

        tool_map = {}

        for tool in data["tools"]:
            path = tool["path"]
            name = tool["name"]

            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Add dynamically generated function as tool
            tool_map[name] = getattr(module, name)

        return tool_map
