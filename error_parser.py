import re

class ErrorParser:
    """
    Parses NodeJS or Python error messages into structured JSON.
    """

    def parse(self, stderr):
        if not stderr:
            return None

        lines = stderr.strip().split("\n")
        message = lines[0]

        trace = []
        for line in lines[1:]:
            m = re.search(r"at (.*?) \((.*?):(\d+):(\d+)\)", line)
            if m:
                trace.append({
                    "function": m.group(1),
                    "file": m.group(2),
                    "line": m.group(3),
                    "column": m.group(4)
                })

        return {
            "message": message,
            "trace": trace
        }
