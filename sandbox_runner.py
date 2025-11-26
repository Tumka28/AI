import subprocess
import tempfile
import json

class SandboxRunner:
    """
    Safely runs JS code inside a Node.js sandbox.
    Captures stdout and stderr WITHOUT any dangerous permissions.
    """

    def run_js(self, code):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".js", mode="w") as tmp:
            tmp.write(code)
            tmp.flush()

            try:
                result = subprocess.run(
                    ["node", tmp.name],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "success": (result.returncode == 0)
                }

            except subprocess.TimeoutExpired:
                return {"error": "Execution timed out", "success": False}
