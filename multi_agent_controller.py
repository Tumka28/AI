from utils.llm_client import LLMClient
from AI.MultiAgent2.agents import PlannerAgent, CoderAgent, ReviewerAgent, CriticAgent
from AI.MultiAgent2.debate_engine import DebateEngine
from AI.MultiAgent2.agreement_engine import AgreementEngine

class MultiAgentController2:
    """
    Planner -> Debate -> Coding -> Review -> Critique -> Agreement
    """

    def __init__(self):
        self.llm = LLMClient()
        self.planner = PlannerAgent("Planner", self.llm)
        self.coder = CoderAgent("Coder", self.llm)
        self.reviewer = ReviewerAgent("Reviewer", self.llm)
        self.critic = CriticAgent("Critic", self.llm)

        self.debate_engine = DebateEngine()
        self.agreement_engine = AgreementEngine()

    def run(self, goal):
        # 1) Planning
        plan = self.planner.plan(goal)

        # 2) Debate between Planner + Critic
        debate_result = self.debate_engine.debate(
            [self.planner, self.critic],
            plan,
            rounds=2
        )

        # 3) Coding
        code = self.coder.code(plan)

        # 4) Review
        review = self.reviewer.review(code)

        # 5) Critique + Agreement
        agreement = self.agreement_engine.agree(
            [self.planner, self.coder, self.reviewer, self.critic],
            goal,
            self.llm
        )

        return {
            "goal": goal,
            "plan": plan,
            "debate": debate_result,
            "code": code,
            "review": review,
            "agreement": agreement
        }
