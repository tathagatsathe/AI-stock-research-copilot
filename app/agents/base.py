from abc import ABC, abstractmethod


class BaseAgent(ABC):
    @abstractmethod
    def run(self, **kwargs) -> dict:
        """Execute agent logic and return a JSON-serializable result."""
