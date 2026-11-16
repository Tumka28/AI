from bot_v.agents.base_agent import BaseAgent

class VisionAgent(BaseAgent):
    def describe(self, img_path):
        return self.llm.query_image(
            "vision",
            "Describe the content of this image.",
            img_path
        )
