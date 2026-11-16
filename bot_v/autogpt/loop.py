from bot_v.autogpt.controller import AutoGPTController

autogpt = AutoGPTController()

def run_autogpt(goal):
    return autogpt.run(goal)
