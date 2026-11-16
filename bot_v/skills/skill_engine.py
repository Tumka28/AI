from bot_v.skills.skill_extractor import SkillExtractor
from bot_v.skills.tool_registry import ToolRegistry
from bot_v.skills.auto_tool_generator import AutoToolGenerator

class SkillEngine:
    """
    Main system:
    - Extract reusable skills from code
    - Generate new tools
    - Register them into JSON schema
    """

    def __init__(self):
        self.extractor = SkillExtractor()
        self.registry = ToolRegistry()
        self.generator = AutoToolGenerator()

    def learn_from_code(self, code):
        # 1) Extract patterns
        skills = self.extractor.extract(code)

        generated = []

        for skill in skills:
            if skill["type"] == "function":
                name = skill["name"]
                params = skill["params"]

                # 2) Generate Python tool file
                try:
                    tool_file = self.generator.create_tool_file(name, params)
                except ValueError:
                    continue

                # 3) Register it
                tool = {"name": name, "params": params, "path": tool_file}
                self.registry.add_tool(tool)
                generated.append(tool)

        return generated
