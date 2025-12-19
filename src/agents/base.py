from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AgentResponse:
    """Standard response from an agent."""
    success: bool
    data: Any
    message: str
    agent_name: str
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "agent": self.agent_name,
            "error": self.error,
        }


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def process(self, query: str, **kwargs) -> AgentResponse:
        pass
    
    @abstractmethod
    def can_handle(self, query: str) -> bool:
        pass
