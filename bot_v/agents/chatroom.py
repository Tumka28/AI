from bot_v.agents.planner_agent import PlannerAgent
from bot_v.agents.coder_agent import CoderAgent
from bot_v.agents.reviewer_agent import ReviewerAgent
from bot_v.agents.debug_agent import DebugAgent
from bot_v.agents.vision_agent import VisionAgent
from bot_v.agents.memory_agent import MemoryAgent
from bot_v.llm.client import LLMClient

class AgentChatroom:
    def __init__(self):
        llm = LLMClient()

        self.memory = MemoryAgent()

        self.planner = PlannerAgent("Planner", llm)
        self.coder   = CoderAgent("Coder", llm)
        self.reviewer= ReviewerAgent("Reviewer", llm)
        self.debugger= DebugAgent("Debugger", llm)
        self.vision  = VisionAgent("Vision", llm)

    def run(self, user_request):
        self.memory.add("User", user_request)

        # Step 1: Planner creates a plan
        plan = self.planner.plan(user_request)
        self.memory.add("Planner", plan)

        # Step 2: Coder writes code
        code = self.coder.write(user_request)
        self.memory.add("Coder", code)

        # Step 3: Reviewer checks code
        review = self.reviewer.review(code)
        self.memory.add("Reviewer", review)

        # Step 4: Debugger fixes issues
        fixed = self.debugger.fix(code)
        self.memory.add("Debugger", fixed)

        # Final output to user
        return {
            "plan": plan,
            "code": fixed,
            "review": review,
            "log": self.memory.get_context()
        }
