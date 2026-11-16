from bot_v.agents.coder_agent import CoderAgent
from bot_v.debugger.self_debugger import SelfDebugger
from bot_v.llm.client import LLMClient

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
