from AI.Debugger.sandbox_runner import SandboxRunner
from AI.Debugger.error_parser import ErrorParser
from AI.Debugger.auto_fixer import AutoFixer

class SelfDebugger:
    """
    Code → Run → Error → Fix → Run again (loop)
    """

    def __init__(self):
        self.runner = SandboxRunner()
        self.parser = ErrorParser()
        self.fixer = AutoFixer()

    def debug(self, code):
        # 1. RUN CODE
        result = self.runner.run_js(code)

        # Runs successfully
        if result["success"]:
            return {
                "status": "success",
                "output": result["stdout"],
                "fixed_code": code
            }

        # 2. PARSE ERROR
        err = self.parser.parse(result["stderr"])
        if not err:
            return {"status": "unknown_error", "error": result["stderr"]}

        # 3. AUTO-FIX USING DEEPSEEK-CODER
        fixed = self.fixer.fix(code, err)

        # 4. RUN AGAIN
        result2 = self.runner.run_js(fixed)

        return {
            "status": "fixed" if result2["success"] else "failed",
            "original_error": err,
            "output": result2["stdout"],
            "fixed_code": fixed
        }
