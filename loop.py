from AI.AutoGPT.controller import AutoGPTController

autogpt = AutoGPTController()

def run_autogpt(goal):
    return autogpt.run(goal)
