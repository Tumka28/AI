from utils.llm_client import LLMClient

class FileGenerator:
    """
    Generates file content based on file path + project idea.
    """

    def __init__(self):
        self.llm = LLMClient()

    def generate_file(self, file_path, project_description):
        code = self.llm.query(
            "deepseek-coder-v2:16b",
            f"""
Generate the file '{file_path}' for project:

{project_description}

Write high-quality, clean code.
Return ONLY the file content. No explanations.
"""
        )
        return code
