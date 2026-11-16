import os

class ProjectScanner:
    """
    Scans entire project folder and loads all files into memory.
    """

    def scan(self, root_dir):
        project_files = []

        for folder, _, files in os.walk(root_dir):
            for f in files:
                if f.endswith((".js", ".py", ".json", ".html", ".css")):
                    full_path = os.path.join(folder, f)
                    rel_path = os.path.relpath(full_path, root_dir)

                    with open(full_path, "r", encoding="utf8", errors="ignore") as file:
                        content = file.read()

                    project_files.append({
                        "path": rel_path,
                        "content": content
                    })

        return project_files
