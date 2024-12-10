from typing import Dict, List, Optional
from dataclasses import dataclass, field
import asyncio
import logging
from datetime import datetime

from ..models.shop import PrintShop, ShopStatus, Capability, InventoryItem
from ..models.order import Order, OrderStatus
from ..infrastructure.messaging.types import MessageTypes

logger = logging.getLogger(__name__)

@dataclass
class NodeState:
    """Tracks runtime state of a node"""
    active_orders: Dict[str, Order] = field(default_factory=dict)
    production_queue: List[str] = field(default_factory=list)
    order_history: List[str] = field(default_factory=list)
    current_capacity: int = 0
    status: ShopStatus = ShopStatus.ONLINE
    inventory: Dict[str, InventoryItem] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=datetime.now)

class PrintShopNode:
    def __init__(
        self,
        shop: PrintShop,
        message_transport: MessageTransport
    ):
        self.shop = shop
        self.state = NodeState(current_capacity=self.shop.daily_capacity)
        self.transport = message_transport
        self.heartbeat_interval = 30
        self.max_queue_size = 100

    async def start(self):
        """Start node operations"""
        # Announce node presence
        hello_msg = {
            "type": MessageTypes.NODE_HELLO,
            "data": {
                "shop_id": self.shop.id,
                "location": self.shop.location.to_dict(),
                "capabilities": [cap.value for cap in self.shop.capabilities],
                "capacity": self.shop.daily_capacity
            }
        }
        await self.protocol.send_message(hello_msg)

        # Start operational loops
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._process_production_queue())
        logger.info(f"Node {self.shop.id} started")
        
    async def join_cluster(self, cluster_id: str):
        """Request to join a specific cluster"""
        await self.transport.publish(f"cluster.{cluster_id}.join", {
            "node_id": self.shop.id,
            "location": self.shop.location.to_dict(),
            "capabilities": [cap.value for cap in self.shop.capabilities],
            "capacity": self.state.current_capacity
        })

    async def stop(self):
        """Stop node operations"""
        bye_msg = {
            "type": MessageTypes.NODE_BYE,
            "data": {"shop_id": self.shop.id}
        }
        await self.protocol.send_message(bye_msg)
        self.state.status = ShopStatus.OFFLINE
        logger.info(f"Node {self.shop.id} stopped")

    async def handle_order(self, order: Order) -> bool:
        """Process incoming order"""
        try:
            if self._can_handle_order(order):
                if len(self.state.production_queue) < self.max_queue_size:
                    # Accept the order
                    self.state.production_queue.append(order.id)
                    self.state.active_orders[order.id] = order
                    
                    # Reserve capacity
                    total_quantity = sum(item.quantity for item in order.items)
                    self.reserve_capacity(total_quantity)
                    
                    # Notify order accepted
                    msg = {
                        "type": MessageTypes.ORDER_ALLOCATED,
                        "data": {
                            "order_id": order.id,
                            "node_id": self.shop.id,
                            "estimated_completion": datetime.now().isoformat()  # TODO: Add real estimation
                        }
                    }
                    await self.transport.publish(f"{msg['type']}", msg['data'])
                    
                    logger.info(f"Node {self.shop.id} accepted order {order.id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error handling order {order.id}: {e}")
            return False

    def _can_handle_order(self, order: Order) -> bool:
        """Check if node can handle the order"""
        total_quantity = sum(item.quantity for item in order.items)
        
        if not self.has_capacity(total_quantity):
            return False

        for item in order.items:
            if not self.can_fulfill_item(item.product_type, item.quantity, sku=item.sku):
                return False

        return True

    async def _heartbeat_loop(self):
        """Periodic heartbeat"""
        while True:
            try:
                self.state.last_heartbeat = datetime.now()
                
                msg = {
                    "type": MessageTypes.NODE_HEARTBEAT,
                    "data": {
                        "node_id": self.shop.id,
                        "status": self.state.status.value,
                        "capacity": {
                            "current": self.state.current_capacity,
                            "total": self.shop.daily_capacity
                        },
                        "timestamp": self.state.last_heartbeat.isoformat()
                    }
                }
                await self.transport.publish(f"{msg['type']}", msg['data'])

            except Exception as e:
                logger.error(f"Error in heartbeat: {e}")
            await asyncio.sleep(self.heartbeat_interval)

    async def _process_production_queue(self):
        """Process orders in the production queue"""
        while True:
            try:
                if self.state.production_queue:
                    order_id = self.state.production_queue[0]
                    order = self.state.active_orders.get(order_id)

                    if order:
                        # Start production
                        msg = {
                            "type": MessageTypes.ORDER_STARTED,
                            "data": {
                                "order_id": order.id,
                                "node_id": self.shop.id,
                                "start_time": datetime.now().isoformat()
                            }
                        }
                        await self.transport.publish(f"{msg['type']}", msg['data'])
                        
                        # Simulate production
                        await self._produce_order(order)
                        
                        # Complete order
                        self.state.production_queue.pop(0)
                        self.state.order_history.append(order_id)
                        del self.state.active_orders[order_id]
                        
                        # Notify completion
                        msg = {
                            "type": MessageTypes.ORDER_COMPLETED,
                            "data": {
                                "order_id": order.id,
                                "node_id": self.shop.id,
                                "completion_time": datetime.now().isoformat()
                            }
                        }
                        await self.transport.publish(f"{msg['type']}", msg['data'])
                        
                        logger.info(f"Node {self.shop.id} completed order {order_id}")

            except Exception as e:
                logger.error(f"Error processing production queue: {e}")
            await asyncio.sleep(5)

    async def _produce_order(self, order: Order):
        """Simulate order production"""
        production_time = order.estimated_production_time()
        await asyncio.sleep(min(production_time, 10))
        
        # Release capacity
        total_quantity = sum(item.quantity for item in order.items)
        self.release_capacity(total_quantity)

    def handle_message(self, message: dict):
        """Handle incoming messages"""
        msg_type = message.get("type")
        data = message.get("data", {})

        handlers = {
            MessageTypes.ORDER_NEW: self._handle_new_order,
            MessageTypes.NODE_STATUS: self._handle_status_update,
            MessageTypes.INVENTORY_QUERY: self._handle_inventory_query,
            MessageTypes.INVENTORY_UPDATE: self._handle_inventory_update
        }

        handler = handlers.get(msg_type)
        if handler:
            asyncio.create_task(handler(data))
        else:
            logger.warning(f"No handler for message type: {msg_type}")

    async def _handle_new_order(self, data: dict):
        """Handle new order request"""
        try:
            order = Order.from_dict(data)
            await self.handle_order(order)
        except Exception as e:
            logger.error(f"Error handling new order: {e}")

    async def _handle_status_update(self, data: dict):
        """Handle status update request"""
        try:
            new_status = ShopStatus(data["status"])
            self.update_status(new_status, data.get("reason"))
        except Exception as e:
            logger.error(f"Error handling status update: {e}")

    async def _handle_inventory_query(self, data: dict):
        """Handle inventory query"""
        try:
            sku = data["sku"]
            quantity = self.state.inventory.get(sku, {}).get("quantity", 0)
            
            msg = {
                "type": MessageTypes.INVENTORY_UPDATE,
                "data": {
                    "sku": sku,
                    "quantity": quantity,
                    "node_id": self.shop.id
                }
            }
            await self.transport.publish(f"{msg['type']}", msg['data'])
        except Exception as e:
            logger.error(f"Error handling inventory query: {e}")

    async def _handle_inventory_update(self, data: dict):
        """Handle inventory update"""
        try:
            sku = data["sku"]
            quantity = data["quantity"]
            self.update_inventory(sku, quantity)
        except Exception as e:
            logger.error(f"Error handling inventory update: {e}")

    # [Core methods like update_status, has_capacity, reserve_capacity, etc. remain unchanged]

    # -----------------------
    # Runtime Methods Moved from PrintShop
    # -----------------------

    def has_capacity(self, quantity: int) -> bool:
        return (
            self.state.status == ShopStatus.ONLINE and
            self.state.current_capacity >= quantity
        )

    def reserve_capacity(self, quantity: int) -> bool:
        if self.has_capacity(quantity):
            self.state.current_capacity -= quantity
            return True
        return False

    def release_capacity(self, quantity: int):
        self.state.current_capacity = min(
            self.shop.daily_capacity,
            self.state.current_capacity + quantity
        )

    def update_inventory(self, sku: str, quantity: int):
        if sku in self.state.inventory:
            item = self.state.inventory[sku]
            item.quantity = quantity
            item.last_updated = datetime.now()
        else:
            self.state.inventory[sku] = InventoryItem(
                sku=sku,
                quantity=quantity,
                reorder_point=50,
                max_quantity=1000
            )

    def can_fulfill_item(self, product_type: Capability, quantity: int, sku: Optional[str] = None) -> bool:
        if product_type not in self.shop.capabilities:
            return False

        if not self.has_capacity(quantity):
            return False

        if sku and sku in self.state.inventory:
            return self.state.inventory[sku].quantity >= quantity

        return True

    def get_low_inventory_items(self) -> List[InventoryItem]:
        return [item for item in self.state.inventory.values() if item.needs_reorder()]

    def get_status_summary(self) -> dict:
        """Get summary of shop + node runtime status"""
        utilization = (self.shop.daily_capacity - self.state.current_capacity) / self.shop.daily_capacity if self.shop.daily_capacity > 0 else 0
        return {
            "id": self.shop.id,
            "name": self.shop.name,
            "status": self.state.status.value,
            "location": {
                "lat": self.shop.location.latitude,
                "lon": self.shop.location.longitude
            },
            "capabilities": [cap.value for cap in self.shop.capabilities],
            "capacity": {
                "daily": self.shop.daily_capacity,
                "available": self.state.current_capacity,
                "utilization": utilization
            },
            "active_orders": len(self.state.active_orders),
            "inventory_status": {
                "total_skus": len(self.state.inventory),
                "low_stock_items": len(self.get_low_inventory_items())
            },
            "last_heartbeat": self.state.last_heartbeat.isoformat()
        }
        
    def update_status(self, new_status: ShopStatus, reason: Optional[str] = None) -> Dict:
        old_status = self.state.status
        self.state.status = new_status
        self.state.last_heartbeat = datetime.now()

        return {
            "timestamp": self.state.last_heartbeat,
            "shop_id": self.shop.id,
            "old_status": old_status.value,
            "new_status": new_status.value,
            "reason": reason
        }

    def is_healthy(self, max_heartbeat_age_seconds: int = 300) -> bool:
        if self.state.status == ShopStatus.OFFLINE:
            return False
        heartbeat_age = (datetime.now() - self.state.last_heartbeat).total_seconds()
        return heartbeat_age <= max_heartbeat_age_seconds

    # -----------------------
    # Node-Specific Methods
    # -----------------------

    def get_status(self) -> Dict:
        """Get current node status"""
        return {
            "node_id": self.shop.id,
            "status": self.state.status.value,
            "capacity": {
                "total": self.shop.daily_capacity,
                "current": self.state.current_capacity
            },
            "orders": {
                "active": len(self.state.active_orders),
                "queue": len(self.state.production_queue),
                "completed": len(self.state.order_history)
            },
            "inventory": {
                "total_skus": len(self.state.inventory),
                "low_stock": len(self.get_low_inventory_items())
            },
            "last_heartbeat": self.state.last_heartbeat.isoformat()
        }