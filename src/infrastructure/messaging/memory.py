from typing import Dict, Callable, Set
from collections import defaultdict
import asyncio
import logging
from datetime import datetime

from .interface import MessageTransport
from .types import MessageTypes

logger = logging.getLogger(__name__)

class InMemoryMessageTransport(MessageTransport):
    def __init__(self):
        self._subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        self._message_count = 0
        self._start_time = datetime.now()
        # Add storage for published messages for testing
        self.published_messages: Dict[str, list] = defaultdict(list)

    async def publish(self, topic: str, message: dict) -> bool:
        """Publish message to all topic subscribers"""
        self._message_count += 1
        
        # Store message for test verification
        self.published_messages[topic].append(message)

        # Add metadata to message
        message.update({
            "_metadata": {
                "topic": topic,
                "timestamp": datetime.now().isoformat(),
                "message_id": f"msg_{self._message_count}"
            }
        })

        # Schedule callback execution for each subscriber
        tasks = []
        for callback in self._subscribers[topic]:
            tasks.append(self._execute_callback(callback, message.copy()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return True if tasks else False

    async def subscribe(self, topic: str, callback: Callable[[dict], None]) -> None:
        """Subscribe callback to topic"""
        self._subscribers[topic].add(callback)
        logger.debug(f"Added subscriber to topic: {topic}")

    async def unsubscribe(self, topic: str, callback: Callable[[dict], None]) -> None:
        """Remove callback from topic subscribers"""
        if topic in self._subscribers:
            self._subscribers[topic].discard(callback)
            if not self._subscribers[topic]:
                del self._subscribers[topic]
            logger.debug(f"Removed subscriber from topic: {topic}")

    async def _execute_callback(self, callback: Callable[[dict], None], message: dict):
        """Execute callback with error handling"""
        try:
            await callback(message)
        except Exception as e:
            logger.error(f"Error in message callback: {e}")