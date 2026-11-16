from bot_v.project.scanner import ProjectScanner
from bot_v.project.refactor_agent import RefactorAgent
from bot_v.project.writer import ProjectWriter

class ProjectRefactorer:
    """
    Full pipeline:
    1) Scan project
    2) Refactor each file using DeepSeek
    3) Write improved project
    """

    def __init__(self):
        self.scanner = ProjectScanner()
        self.agent = RefactorAgent()
        self.writer = ProjectWriter()

    def refactor_project(self, root_dir, output_dir="refactored_project"):
        # 1. Scan
        files = self.scanner.scan(root_dir)

        improved_files = []

        # 2. Refactor each file
        for f in files:
            new_content = self.agent.refactor(f["path"], f["content"])
            improved_files.append({
                "path": f["path"],
                "content": new_content
            })

        # 3. Write improved project
        self.writer.write(output_dir, improved_files)

        return {
            "status": "done",
            "files_processed": len(files),
            "output_dir": output_dir
        }
