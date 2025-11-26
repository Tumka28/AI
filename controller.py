from AI.AutoGPT.planner import AutoPlanner
from AI.AutoGPT.executor import AutoExecutor
from AI.AutoGPT.improver import AutoImprover

class AutoGPTController:
    """
    Full loop:
    1) Reason → Create plan
    2) Execute each step (code → run → debug)
    3) Improve result
    4) Output final result
    """

    def __init__(self):
        self.planner = AutoPlanner()
        self.executor = AutoExecutor()
        self.improver = AutoImprover()

    def run(self, goal):
        # 1. PLAN
        steps = self.planner.plan(goal)

        results = []

        for step in steps:
            # 2. EXECUTE each step
            out = self.executor.execute_step(step)
            results.append(out)

        # take last code for improvement
        final_code = results[-1]["code"]
        output = results[-1].get("output", "")

        # 3. IMPROVE the final code
        improved = self.improver.improve(final_code, output)

        return {
            "goal": goal,
            "plan": steps,
            "steps_output": results,
            "final_code": improved
        }
