from abc import ABC, abstractmethod
from typing import Callable

class MessageTransport(ABC):
    """Interface for distributed message transport"""
    @abstractmethod
    async def publish(self, topic: str, message: dict) -> bool:
        """Publish message to a topic"""
        pass

    @abstractmethod
    async def subscribe(self, topic: str, callback: Callable[[dict], None]) -> None:
        """Subscribe to messages on a topic with a callback"""
        pass

    @abstractmethod
    async def unsubscribe(self, topic: str, callback: Callable[[dict], None]) -> None:
        """Unsubscribe callback from a topic"""
        pass