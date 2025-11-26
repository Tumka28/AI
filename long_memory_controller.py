from AI.LongMemory.integration_agent import MemoryIntegration

class LongMemoryController:
    """
    Full continuous learning memory controller.
    """

    def __init__(self):
        self.memory = MemoryIntegration()

    def process(self, agent_name, user_input, agent_fn):
        # 1) enrich with memory
        enriched = self.memory.enrich_prompt(agent_name, user_input)

        # 2) agent produces output
        response = agent_fn(enriched)

        # 3) save new interaction to long-term memory
        self.memory.store_interaction(f"{agent_name}: {response}")

        return response
