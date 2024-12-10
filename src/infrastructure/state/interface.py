# Other components can import and depend on just the interface, 
# not any specific implementation. They don't need to know or care if we're using memory, Redis, or something else.

from abc import ABC, abstractmethod
from typing import Any, Optional, List

class StateStore(ABC):
    """Interface for distributed state storage"""
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value for key"""
        pass

    @abstractmethod
    async def put(self, key: str, value: Any) -> bool:
        """Store value at key"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key"""
        pass

    @abstractmethod
    async def list_prefix(self, prefix: str) -> List[str]:
        """List all keys with given prefix"""
        pass