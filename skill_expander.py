from AI.SkillExpansion.pattern_detector import PatternDetector
from AI.SkillExpansion.skill_generator import SkillGenerator
from AI.SkillExpansion.schema_manager import SchemaManager
from AI.SkillExpansion.integration_updater import IntegrationUpdater

class SkillExpander:
    """
    Full automatic skill-expansion system:
    - detect patterns
    - generate skill tool files
    - add them to registry
    - reload tool map
    """

    def __init__(self):
        self.detector = PatternDetector()
        self.generator = SkillGenerator()
        self.schema = SchemaManager()
        self.integrator = IntegrationUpdater()

    def expand_skills(self, code):
        patterns = self.detector.detect(code)
        new_skills = []

        for p in patterns:
            if p["type"] == "function":
                name = p["name"]
                params = p["params"]

                tool_path = self.generator.generate(name, params)
                self.schema.add_tool(name, params, tool_path)
                new_skills.append(name)

        # Return updated skillset to AI Brain
        return {
            "new_skills": new_skills,
            "tool_map": self.integrator.load_tools()
        }
