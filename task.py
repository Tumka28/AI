class Task:
    """
    Represents a task inside the Auto Task Manager.
    """

    def __init__(self, id, description, priority=5, deps=None):
        self.id = id
        self.description = description
        self.priority = priority
        self.deps = deps or []     # Task IDs this task depends on
        self.done = False

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "deps": self.deps,
            "done": self.done
        }
