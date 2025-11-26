from AI.Agents.coder_agent import CoderAgent
from AI.Debugger.self_debugger import SelfDebugger
from utils.llm_client import LLMClient

class AutoExecutor:
    """
    Executes a plan step:
    - writes code
    - runs code
    - self-debug until fixed
    """

    def __init__(self):
        self.llm = LLMClient()
        self.coder = CoderAgent("AutoCoder", self.llm)
        self.debugger = SelfDebugger()

    def execute_step(self, step):
        # 1) Write code
        code = self.coder.write(step)

        # 2) Debug it
        result = self.debugger.debug(code)

        # Return improved code
        return {
            "step": step,
            "code": result["fixed_code"],
            "status": result["status"],
            "output": result.get("output", "")
        }
