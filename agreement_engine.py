from AI.MultiAgent2.agents import SummarizerAgent

class AgreementEngine:
    """
    Agents discuss until their answers converge.
    """

    def agree(self, agents, topic, llm, max_rounds=5):
        summary_agent = SummarizerAgent("Summary", llm)
        prev = ""

        for _ in range(max_rounds):
            opinions = []

            for agent in agents:
                resp = agent.think(topic)
                agent.add_memory(resp)
                opinions.append(resp)

            summary = summary_agent.summarize(opinions)

            # If repeated → agreement
            if summary.strip() == prev.strip():
                break

            prev = summary

        return {"final": prev, "opinions": opinions}
