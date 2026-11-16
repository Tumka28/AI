class DebateEngine:
    """
    Multi-agent debate engine.
    """

    def debate(self, agents, topic, rounds=3):
        history = []
        current = topic

        for r in range(rounds):
            round_msgs = []

            for agent in agents:
                resp = agent.think(f"Debate topic:\n{current}")
                agent.add_memory(resp)

                msg = f"{agent.name}: {resp}"
                round_msgs.append(msg)

            # merge opinions
            current = "\n".join(round_msgs)
            history.append(current)

        return history
