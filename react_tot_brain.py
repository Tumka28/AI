from reasoning.tot_generator import ToTGenerator
from reasoning.branch_evaluator import BranchEvaluator
from reasoning.react_engine import ReActEngine

class ReActToTBrain:
    """
    Full Brain:
    1) Tree-of-Thought
    2) Best branch selection
    3) ReAct loop decision execution
    """
    def __init__(self, tool_map, memory):
        self.tot = ToTGenerator()
        self.eval = BranchEvaluator()
        self.react = ReActEngine(tool_map, memory)

    def answer(self, prompt):
        # 1. Generate thoughts
        branches = self.tot.generate_branches(prompt)

        # 2. Select strongest reasoning
        best_branch, score = self.eval.evaluate(prompt, branches)

        # 3. Use ReAct with reasoning context
        context = f"Best reasoning branch: {best_branch}"
        final_answer = self.react.run(prompt + "\n" + context)

        return final_answer
