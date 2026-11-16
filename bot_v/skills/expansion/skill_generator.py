import re

from bot_v.config import data_path

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SkillGenerator:
    """
    Generates Python tool files from detected patterns.
    """

    def generate(self, name, params):
        # Only plain identifiers: keeps the file valid Python and inside data/.
        if not _IDENT.match(name) or not all(_IDENT.match(p) for p in params):
            raise ValueError(f"invalid skill name or params: {name!r} {params!r}")

        file_path = str(data_path("skill_expansion", f"generated_{name}.py"))

        args = ", ".join(params)

        template = f"""
# Auto-generated skill tool
def {name}({args}):
    return "Skill [{name}] executed with args: {args}"
"""

        with open(file_path, "w") as f:
            f.write(template)

        return file_path
