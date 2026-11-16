import os

class FileScanner:
    """
    Scans project files and loads their content.
    """

    def scan(self, root="."):
        files = []

        for folder, _, fs in os.walk(root):
            for f in fs:
                if f.endswith((".js", ".py", ".html", ".css", ".json")):
                    path = os.path.join(folder, f)
                    try:
                        with open(path, "r", encoding="utf8") as fh:
                            content = fh.read()
                        files.append({"path": path, "content": content})
                    except:
                        pass

        return files
