import os


class ProjectWriter:
    """
    Writes improved project files to a clean output folder.
    """

    @staticmethod
    def _safe_path(output_dir, rel_path):
        # File names can come from an LLM: never write outside output_dir.
        root = os.path.realpath(output_dir)
        target = os.path.realpath(os.path.join(root, rel_path))
        if os.path.commonpath([root, target]) != root or target == root:
            raise ValueError(f"refusing to write outside {output_dir}: {rel_path!r}")
        return target

    def write(self, output_dir, files):
        os.makedirs(output_dir, exist_ok=True)

        for f in files:
            new_path = self._safe_path(output_dir, f["path"])
            os.makedirs(os.path.dirname(new_path), exist_ok=True)

            with open(new_path, "w", encoding="utf8") as file:
                file.write(f["content"])

        return True

    def write_project(self, structure, output_dir):
        """Write a nested {"dir": {"file": "content"}} tree (ProjectBuilder)."""
        files = []

        def walk(tree, prefix):
            for name, value in tree.items():
                path = os.path.join(prefix, name) if prefix else name
                if isinstance(value, dict):
                    walk(value, path)
                else:
                    files.append({"path": path, "content": value or ""})

        walk(structure, "")
        return self.write(output_dir, files)
