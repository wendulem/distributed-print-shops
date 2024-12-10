from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
import asyncio
import logging
from datetime import datetime

from ..models.shop import PrintShop, ShopStatus, Location, Capability, InventoryItem
from ..models.order import Order, OrderItem, OrderStatus
from ..models.cluster import Cluster  # Assumed interface for cluster operations
from ..protocol import NetworkProtocol, MessageType  # Assumed protocol classes/enums
from ..routing import Routing  # Assumed routing logic

logger = logging.getLogger(__name__)

@dataclass
class NodeState:
    """Tracks runtime state of a node"""
    active_orders: Dict[str, Order] = field(default_factory=dict)
    neighbors: Dict[str, 'PrintShopNode'] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    order_history: List[str] = field(default_factory=list)
    production_queue: List[str] = field(default_factory=list)
    current_capacity: int = 0
    status: ShopStatus = ShopStatus.ONLINE
    inventory: Dict[str, InventoryItem] = field(default_factory=dict)

class PrintShopNode:
    def __init__(self, shop: PrintShop, cluster: Optional[Cluster] = None, protocol: Optional[NetworkProtocol] = None, routing: Optional[Routing] = None):
        self.shop = shop
        self.state = NodeState(
            current_capacity=self.shop.daily_capacity,
            status=ShopStatus.ONLINE
        )
        self.cluster = cluster  # The cluster this node belongs to
        self.protocol = protocol if protocol else NetworkProtocol()  # Communication protocol
        self.routing = routing if routing else Routing()

        self.heartbeat_interval = 30  # seconds
        self.max_queue_size = 100
        self.max_neighbors = 10  # Limit number of direct neighbors

    async def start(self):
        """Start node operations"""
        if self.cluster:
            # If we have a cluster object, we let the cluster handle node registration.
            # For example: self.cluster.add_node(self) if that's the interface.
            pass

        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._process_production_queue())
        logger.info(f"Node {self.shop.id} started")

    def add_neighbor(self, neighbor: 'PrintShopNode') -> bool:
        """Add a neighboring node (at the node level, not cluster level)"""
        if len(self.state.neighbors) >= self.max_neighbors:
            # Remove furthest neighbor if at capacity
            furthest_neighbor = max(
                self.state.neighbors.values(),
                key=lambda n: self.shop.location.distance_to(n.shop.location)
            )
            self.remove_neighbor(furthest_neighbor.shop.id)

        self.state.neighbors[neighbor.shop.id] = neighbor
        logger.info(f"Node {self.shop.id} added neighbor {neighbor.shop.id}")
        return True

    def remove_neighbor(self, neighbor_id: str):
        """Remove a neighboring node"""
        if neighbor_id in self.state.neighbors:
            del self.state.neighbors[neighbor_id]
            logger.info(f"Node {self.shop.id} removed neighbor {neighbor_id}")

    async def handle_order(self, order: Order) -> bool:
        """Process incoming order"""
        try:
            if self._can_handle_order(order):
                # We can handle it directly
                if len(self.state.production_queue) < self.max_queue_size:
                    self.state.production_queue.append(order.id)
                    self.state.active_orders[order.id] = order
                    order.add_status_update(
                        OrderStatus.ASSIGNED,
                        f"Assigned to shop {self.shop.id}"
                    )
                    logger.info(f"Node {self.shop.id} accepted order {order.id}")
                    return True
            else:
                # Use routing logic to determine if we should forward to another cluster or node
                target_node = self.routing.find_best_node_for_order(order, self.cluster)
                if target_node and target_node != self:
                    # Forward the order as a protocol message
                    msg = self.protocol.create_message(MessageType.ORDER_REQUEST, {
                        "order_id": order.id,
                        "customer_location": {
                            "lat": order.customer_location.latitude,
                            "lon": order.customer_location.longitude
                        },
                        "items": [item.to_dict() for item in order.items]
                    })
                    self.send_message(msg, target_node.shop.id)
                    logger.info(f"Node {self.shop.id} forwarded order {order.id} to {target_node.shop.id}")
                    return True

            return False
        except Exception as e:
            logger.error(f"Error handling order {order.id}: {e}")
            return False

    def _can_handle_order(self, order: Order) -> bool:
        """Check if node can handle the order using runtime checks and static capabilities"""
        total_quantity = sum(item.quantity for item in order.items)
        
        # Check capacity
        if not self.has_capacity(total_quantity):
            return False

        # Check capabilities and inventory
        for item in order.items:
            if not self.can_fulfill_item(item.product_type, item.quantity, sku=item.sku):
                return False

        return True

    async def _heartbeat_loop(self):
        """Periodic heartbeat to maintain node status"""
        while True:
            try:
                self.state.last_heartbeat = datetime.now()

                # Check neighbor health
                unhealthy_neighbors = []
                for neighbor_id, neighbor in self.state.neighbors.items():
                    if not neighbor.is_healthy():
                        unhealthy_neighbors.append(neighbor_id)

                # Remove unhealthy neighbors
                for neighbor_id in unhealthy_neighbors:
                    self.remove_neighbor(neighbor_id)

                # Send heartbeat messages to cluster (if needed)
                if self.cluster:
                    hb_msg = self.protocol.create_message(MessageType.HEARTBEAT, {"node_id": self.shop.id})
                    self.cluster.handle_heartbeat(self, hb_msg)

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
                        # Simulate production time
                        await self._produce_order(order)

                        # Update order status
                        order.add_status_update(
                            OrderStatus.COMPLETED,
                            f"Production completed at {self.shop.id}"
                        )

                        # Update node state
                        self.state.production_queue.pop(0)
                        self.state.order_history.append(order_id)
                        del self.state.active_orders[order_id]

                        logger.info(f"Node {self.shop.id} completed order {order_id}")

            except Exception as e:
                logger.error(f"Error processing production queue: {e}")

            await asyncio.sleep(5)  # Check queue every 5 seconds

    async def _produce_order(self, order: Order):
        """Simulate order production"""
        production_time = order.estimated_production_time()

        order.add_status_update(
            OrderStatus.IN_PRODUCTION,
            f"Production started at {self.shop.id}"
        )

        # Simulate production time (capped at 10s for testing)
        await asyncio.sleep(min(production_time, 10))

        # Release capacity after production
        total_quantity = sum(item.quantity for item in order.items)
        self.release_capacity(total_quantity)

    # -----------------------
    # Runtime Methods Moved from PrintShop
    # -----------------------

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

    def is_healthy(self, max_heartbeat_age_seconds: int = 300) -> bool:
        if self.state.status == ShopStatus.OFFLINE:
            return False
        heartbeat_age = (datetime.now() - self.state.last_heartbeat).total_seconds()
        return heartbeat_age <= max_heartbeat_age_seconds

    # -----------------------
    # Node-Specific Methods
    # -----------------------

    def get_status(self) -> Dict:
        """Get full node status summary including shop and node state"""
        return {
            "shop": self.get_status_summary(),
            "state": {
                "active_orders": len(self.state.active_orders),
                "queue_size": len(self.state.production_queue),
                "neighbor_count": len(self.state.neighbors),
                "orders_completed": len(self.state.order_history),
                "last_heartbeat": self.state.last_heartbeat.isoformat()
            }
        }

    def send_message(self, message: dict, target_id: str) -> bool:
        """Send a protocol message to another node or cluster member"""
        # Using the protocol to send a message; in a real system, this might integrate with I/O
        return self.protocol.send_message(message, target_id)

    def handle_message(self, message: dict, source_id: str):
        """Handle a received protocol message"""
        msg_type = message.get("type")

        if msg_type in (MessageType.CLUSTER_JOIN, MessageType.CLUSTER_LEAVE, MessageType.CLUSTER_UPDATE):
            # Delegate cluster-related message handling to the cluster
            if self.cluster:
                self.cluster.handle_cluster_message(self, message, source_id)
        elif msg_type == MessageType.ORDER_REQUEST:
            # Handle order requests from other nodes
            order_data = message.get("data", {})
            order = Order.from_dict(order_data)  # Assuming a from_dict constructor
            asyncio.create_task(self.handle_order(order))
        elif msg_type == MessageType.HEARTBEAT:
            # Handle heartbeat messages
            # Acknowledge or update health metrics if needed
            pass
        else:
            logger.warning(f"Node {self.shop.id} received unknown message type: {msg_type}")

    # In this refactored version, join_cluster() and leave_cluster() are handled by the Cluster class.
    # The node might call self.cluster.add_node(self) or self.cluster.remove_node(self) as needed, but does not
    # implement cluster logic itself.
