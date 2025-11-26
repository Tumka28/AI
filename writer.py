import os

class ProjectWriter:
    """
    Writes improved project files to a clean output folder.
    """

    def write(self, output_dir, files):
        os.makedirs(output_dir, exist_ok=True)

        for f in files:
            new_path = os.path.join(output_dir, f["path"])
            os.makedirs(os.path.dirname(new_path), exist_ok=True)

            with open(new_path, "w", encoding="utf8") as file:
                file.write(f["content"])

        return True
