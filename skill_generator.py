import os

class SkillGenerator:
    """
    Generates Python tool files from detected patterns.
    """

    def generate(self, name, params):
        file_path = f"AI/SkillExpansion/generated_{name}.py"

        args = ", ".join(params)

        template = f"""
# Auto-generated skill tool
def {name}({args}):
    return "Skill [{name}] executed with args: {args}"
"""

        with open(file_path, "w") as f:
            f.write(template)

        return file_path
