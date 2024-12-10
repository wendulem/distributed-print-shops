from typing import Any, Optional, List, Dict
from .interface import StateStore

class InMemoryStateStore(StateStore):
    """Simple in-memory implementation of StateStore"""
    def __init__(self):
        self._store: Dict[str, Any] = {}

    async def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    async def put(self, key: str, value: Any) -> bool:
        self._store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def list_prefix(self, prefix: str) -> List[str]:
        return [k for k in self._store.keys() if k.startswith(prefix)]