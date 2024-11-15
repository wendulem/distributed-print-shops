from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
import asyncio
import logging
from datetime import datetime

from ..models.order import Order, OrderStatus
from ..models.shop import PrintShop, ShopStatus

logger = logging.getLogger(__name__)

class MessageType(Enum):
    # Node discovery and health
    HELLO = "hello"
    HEARTBEAT = "heartbeat"
    BYE = "bye"
    
    # Order handling
    ORDER_REQUEST = "order_request"
    ORDER_RESPONSE = "order_response"
    ORDER_FORWARD = "order_forward"
    
    # Capacity management
    CAPACITY_UPDATE = "capacity_update"
    CAPACITY_QUERY = "capacity_query"
    
    # Inventory management
    INVENTORY_QUERY = "inventory_query"
    INVENTORY_UPDATE = "inventory_update"
    INVENTORY_TRANSFER = "inventory_transfer"

@dataclass
class Message:
    type: MessageType
    sender_id: str
    receiver_id: Optional[str]
    timestamp: datetime
    payload: Dict[str, Any]
    message_id: str = None
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "message_id": self.message_id
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        data = json.loads(json_str)
        return cls(
            type=MessageType(data["type"]),
            sender_id=data["sender_id"],
            receiver_id=data["receiver_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data["payload"],
            message_id=data["message_id"]
        )

class ProtocolError(Exception):
    """Base class for protocol errors"""
    pass

class NetworkProtocol:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.message_handlers = {
            MessageType.HELLO: self._handle_hello,
            MessageType.HEARTBEAT: self._handle_heartbeat,
            MessageType.BYE: self._handle_bye,
            MessageType.ORDER_REQUEST: self._handle_order_request,
            MessageType.ORDER_RESPONSE: self._handle_order_response,
            MessageType.ORDER_FORWARD: self._handle_order_forward,
            MessageType.CAPACITY_UPDATE: self._handle_capacity_update,
            MessageType.CAPACITY_QUERY: self._handle_capacity_query,
            MessageType.INVENTORY_QUERY: self._handle_inventory_query,
            MessageType.INVENTORY_UPDATE: self._handle_inventory_update,
            MessageType.INVENTORY_TRANSFER: self._handle_inventory_transfer
        }
        self.pending_responses: Dict[str, asyncio.Future] = {}

    async def send_message(self, message: Message) -> Optional[Message]:
        """Send a message and wait for response if needed"""
        try:
            # In a real implementation, this would use actual network communication
            # For now, we'll simulate direct message passing
            
            if message.receiver_id is None:
                # Broadcast message
                # In real implementation, would use proper broadcast mechanism
                logger.info(f"Broadcasting message: {message.type}")
                return None
            
            # For messages that expect responses, create a future
            if message.type in [
                MessageType.ORDER_REQUEST,
                MessageType.CAPACITY_QUERY,
                MessageType.INVENTORY_QUERY
            ]:
                response_future = asyncio.Future()
                self.pending_responses[message.message_id] = response_future
                
                # Simulate network delay
                await asyncio.sleep(0.1)
                
                try:
                    return await asyncio.wait_for(response_future, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for response to {message.type}")
                    return None
                finally:
                    self.pending_responses.pop(message.message_id, None)
            
            return None
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise ProtocolError(f"Failed to send message: {e}")

    async def handle_message(self, message: Message) -> Optional[Message]:
        """Handle incoming message"""
        try:
            handler = self.message_handlers.get(message.type)
            if handler:
                response = await handler(message)
                return response
            else:
                logger.warning(f"No handler for message type: {message.type}")
                return None
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            raise ProtocolError(f"Failed to handle message: {e}")

    async def _handle_hello(self, message: Message) -> Message:
        """Handle node introduction"""
        shop_data = message.payload.get("shop_data")
        if not shop_data:
            raise ProtocolError("Hello message missing shop data")
            
        return Message(
            type=MessageType.HELLO,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "status": "acknowledged",
                "shop_data": {  # Would include own shop data
                    "id": self.node_id,
                    "status": "online"
                }
            }
        )

    async def _handle_heartbeat(self, message: Message) -> None:
        """Handle heartbeat message"""
        # Update last seen timestamp for sender
        # In real implementation, would update node state
        logger.debug(f"Received heartbeat from {message.sender_id}")
        return None

    async def _handle_bye(self, message: Message) -> None:
        """Handle node departure"""
        logger.info(f"Node {message.sender_id} departing network")
        return None

    async def _handle_order_request(self, message: Message) -> Message:
        """Handle incoming order request"""
        order_data = message.payload.get("order")
        if not order_data:
            raise ProtocolError("Order request missing order data")
            
        # In real implementation, would check capacity and respond accordingly
        can_fulfill = True  # Simplified check
        
        return Message(
            type=MessageType.ORDER_RESPONSE,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "order_id": order_data["id"],
                "can_fulfill": can_fulfill,
                "estimated_time": 24.0 if can_fulfill else None
            }
        )

    async def _handle_order_response(self, message: Message) -> None:
        """Handle response to order request"""
        if message.message_id in self.pending_responses:
            future = self.pending_responses[message.message_id]
            if not future.done():
                future.set_result(message)
        return None

    async def _handle_order_forward(self, message: Message) -> Message:
        """Handle forwarded order"""
        order_data = message.payload.get("order")
        if not order_data:
            raise ProtocolError("Forwarded order missing order data")
            
        # Similar to order request, but with forwarding history
        can_fulfill = True  # Simplified check
        
        return Message(
            type=MessageType.ORDER_RESPONSE,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "order_id": order_data["id"],
                "can_fulfill": can_fulfill,
                "estimated_time": 24.0 if can_fulfill else None,
                "forward_count": message.payload.get("forward_count", 0) + 1
            }
        )

    async def _handle_capacity_update(self, message: Message) -> None:
        """Handle capacity update from another node"""
        # Update local view of network capacity
        logger.debug(f"Capacity update from {message.sender_id}")
        return None

    async def _handle_capacity_query(self, message: Message) -> Message:
        """Handle capacity query"""
        return Message(
            type=MessageType.CAPACITY_UPDATE,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "available_capacity": 100,  # Would get real capacity
                "total_capacity": 200
            }
        )

    async def _handle_inventory_query(self, message: Message) -> Message:
        """Handle inventory query"""
        sku = message.payload.get("sku")
        if not sku:
            raise ProtocolError("Inventory query missing SKU")
            
        return Message(
            type=MessageType.INVENTORY_UPDATE,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "sku": sku,
                "quantity": 50  # Would get real inventory level
            }
        )

    async def _handle_inventory_update(self, message: Message) -> None:
        """Handle inventory update"""
        # Update local view of network inventory
        logger.debug(f"Inventory update from {message.sender_id}")
        return None

    async def _handle_inventory_transfer(self, message: Message) -> Message:
        """Handle inventory transfer request"""
        transfer_data = message.payload.get("transfer")
        if not transfer_data:
            raise ProtocolError("Transfer request missing transfer data")
            
        # Would handle actual inventory transfer logic
        success = True  # Simplified response
        
        return Message(
            type=MessageType.INVENTORY_UPDATE,
            sender_id=self.node_id,
            receiver_id=message.sender_id,
            timestamp=datetime.now(),
            payload={
                "transfer_id": transfer_data["id"],
                "success": success
            }
        )