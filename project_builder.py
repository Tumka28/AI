from AI.ProjectGenerator.structure_generator import StructureGenerator
from AI.ProjectGenerator.file_generator import FileGenerator
from AI.ProjectGenerator.writer import ProjectWriter

class ProjectBuilder:
    """
    Combines all generators to create complete project.
    """

    def __init__(self):
        self.structure_gen = StructureGenerator()
        self.file_gen = FileGenerator()
        self.writer = ProjectWriter()

    def build_project(self, description, output_dir="generated_project"):
        # 1) Generate folder structure
        structure = self.structure_gen.generate_structure(description)

        # 2) For each file, generate content
        def fill_content(tree):
            for key, value in tree.items():
                if isinstance(value, dict):
                    fill_content(value)
                else:
                    tree[key] = self.file_gen.generate_file(key, description)

        fill_content(structure)

        # 3) Write project to disk
        self.writer.write_project(structure, output_dir)

        return {
            "status": "done",
            "output": output_dir,
            "structure": structure
        }
