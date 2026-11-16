import re

from bot_v.config import data_path

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AutoToolGenerator:
    """
    Generates callable Python tool functions based on learned skills.
    """

    def create_tool_file(self, name, params):
        # Names come from analysed code; only accept plain identifiers so the
        # generated file is valid Python and the path stays inside data/.
        if not _IDENT.match(name) or not all(_IDENT.match(p) for p in params):
            raise ValueError(f"invalid tool name or params: {name!r} {params!r}")

        file_path = str(data_path("skills", f"generated_{name}.py"))

        args = ", ".join(params)

        template = f"""
# Auto-generated tool
def {name}({args}):
    # Basic auto-generated placeholder
    return f"Auto tool [{name}] executed with: {args}"
"""

        with open(file_path, "w") as f:
            f.write(template)

        return file_path
