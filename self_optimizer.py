from AI.SelfOptimize.performance_analyzer import PerformanceAnalyzer
from AI.SelfOptimize.weakness_detector import WeaknessDetector
from AI.SelfOptimize.self_refactor import SelfRefactor
from AI.SelfOptimize.behavior_optimizer import BehaviorOptimizer
from AI.SelfOptimize.knowledge_refresher import KnowledgeRefresher

class SelfOptimizer:
    """
    Full Self-Optimization Pipeline:
    1) Score AI output
    2) Detect weaknesses
    3) Refactor code
    4) Improve reasoning rules
    5) Update long-term memory
    """

    def __init__(self):
        self.analyzer = PerformanceAnalyzer()
        self.detector = WeaknessDetector()
        self.refactorer = SelfRefactor()
        self.behavior = BehaviorOptimizer()
        self.knowledge = KnowledgeRefresher()

    def optimize(self, code_output):
        score = self.analyzer.score_output(code_output)
        weaknesses = self.detector.detect(code_output)

        improved_code = self.refactorer.refactor_code(code_output, weaknesses)
        improved_rules = self.behavior.optimize_rules(weaknesses)

        self.knowledge.refresh(improved_rules)

        return {
            "score_before": score,
            "weaknesses": weaknesses,
            "improved_code": improved_code,
            "improved_reasoning": improved_rules
        }
