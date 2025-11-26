import re

class PatternDetector:
    """
    Detect patterns in code that can be converted into reusable tools.
    """

    def detect(self, code):
        detected = []

        # Detect function definitions
        for m in re.findall(r"function\s+(\w+)\s*\((.*?)\)", code):
            fn_name, params = m
            params = [p.strip() for p in params.split(",") if p.strip()]
            detected.append({
                "type": "function",
                "name": fn_name,
                "params": params
            })

        # Detect formatting utilities
        if "format" in code.lower():
            detected.append({"type": "pattern", "name": "text_formatter"})

        # Detect conversion utilities
        if "convert" in code.lower():
            detected.append({"type": "pattern", "name": "converter"})

        return detected
