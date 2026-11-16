from bot_v.llm.client import LLMClient

class FileGenerator:
    """
    Generates file content based on file path + project idea.
    """

    def __init__(self):
        self.llm = LLMClient()

    def generate_file(self, file_path, project_description):
        code = self.llm.query(
            "coder",
            f"""
Generate the file '{file_path}' for project:

{project_description}

Write high-quality, clean code.
Return ONLY the file content. No explanations.
"""
        )
        return code
