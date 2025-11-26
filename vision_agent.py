from AI.Agents.base_agent import BaseAgent

class VisionAgent(BaseAgent):
    def describe(self, img_path):
        return self.llm.query_image(
            "llava:7b",
            "Describe the content of this image.",
            img_path
        )
