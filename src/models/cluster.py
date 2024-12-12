from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional
from datetime import datetime
import logging

from .shop import PrintShop, Capability
from .location import Location
from .order import Order, OrderItem
from ..infrastructure.messaging import MessageTransport
from ..infrastructure.messaging.types import MessageTypes

logger = logging.getLogger(__name__)

@dataclass
class ClusterMetrics:
    """Tracks operational metrics for a cluster"""
    total_capacity: int = 0
    available_capacity: int = 0
    active_orders: int = 0
    total_orders_processed: int = 0

    def update_capacity(self, delta: int):
        self.available_capacity += delta

    def record_order(self):
        self.active_orders += 1
        self.total_orders_processed += 1

    def complete_order(self):
        self.active_orders -= 1

@dataclass
class Cluster:
    """
    Represents a geographic cluster of print shops.
    Uses message-based communication for all node interactions.
    """
    id: str
    center_location: Location
    radius_miles: float = 100.0
    metrics: ClusterMetrics = field(default_factory=ClusterMetrics)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.node_ids: Set[str] = set()
        self.node_capabilities: Dict[str, Set[Capability]] = {}
        self.node_capacities: Dict[str, int] = {}

    def __init__(
        self,
        cluster_id: str,
        center_location: Location,
        message_transport: MessageTransport,
        radius_miles: float = 100.0
    ):
        self.id = cluster_id
        self.center_location = center_location
        self.radius_miles = radius_miles
        self.transport = message_transport
        self.metrics = ClusterMetrics()
        self.created_at = datetime.now()
        self.node_ids = set()
        self.node_capabilities = {}
        self.node_capacities = {}

    async def start(self):
        """Start cluster operations"""
        # Subscribe to relevant message topics
        await self.transport.subscribe(f"cluster.{self.id}.join", self._handle_join_request)
        await self.transport.subscribe(f"cluster.{self.id}.leave", self._handle_leave_request)
        await self.transport.subscribe(f"cluster.{self.id}.status", self._handle_status_update)
        await self.transport.subscribe(f"cluster.{self.id}.order", self._handle_order_request)
        
        # Announce cluster presence
        await self.transport.publish(
            "cluster.announce",
            {
                "cluster_id": self.id,
                "location": self.center_location.to_dict(),
                "radius": self.radius_miles
            }
        )
        
        logger.info(f"Cluster {self.id} started")

    async def _handle_join_request(self, message: dict):
        """Handle node join request"""
        data = message.get("data", {})
        node_id = data.get("node_id")
        location = Location(**data.get("location", {}))
        capabilities = {Capability(cap) for cap in data.get("capabilities", [])}
        capacity = data.get("capacity", 0)

        if self._is_in_range(location):
            self.node_ids.add(node_id)
            self.node_capabilities[node_id] = capabilities
            self.node_capacities[node_id] = capacity
            
            self.metrics.total_capacity += capacity
            self.metrics.available_capacity += capacity
            
            await self.transport.publish(
                f"node.{node_id}.cluster",
                {
                    "type": "join_accepted",
                    "cluster_id": self.id
                }
            )
            logger.info(f"Node {node_id} joined cluster {self.id}")

    async def _handle_leave_request(self, message: dict):
        """Handle node leave request"""
        node_id = message.get("data", {}).get("node_id")
        if node_id in self.node_ids:
            capacity = self.node_capacities.get(node_id, 0)
            self.metrics.total_capacity -= capacity
            self.metrics.available_capacity -= capacity
            
            self.node_ids.remove(node_id)
            self.node_capabilities.pop(node_id, None)
            self.node_capacities.pop(node_id, None)
            
            logger.info(f"Node {node_id} left cluster {self.id}")

    async def _handle_status_update(self, message: dict):
        """Handle node status update"""
        data = message.get("data", {})
        node_id = data.get("node_id")
        if node_id in self.node_ids:
            # Update capacity tracking
            old_capacity = self.node_capacities.get(node_id, 0)
            new_capacity = data.get("capacity", {}).get("available", 0)
            delta = new_capacity - old_capacity
            self.metrics.update_capacity(delta)
            self.node_capacities[node_id] = new_capacity

    async def _handle_order_request(self, message: dict):
        """Handle order routing request"""
        data = message.get("data", {})
        order = Order.from_dict(data.get("order", {}))
        
        allocation = await self.allocate_order(order)
        if allocation:
            # Notify successful allocation
            await self.transport.publish(
                "order.allocated",
                {
                    "order_id": order.id,
                    "cluster_id": self.id,
                    "allocation": {
                        node_id: [item.to_dict() for item in items]
                        for node_id, items in allocation.items()
                    }
                }
            )
        else:
            # Notify failed allocation
            await self.transport.publish(
                "order.unallocated",
                {
                    "order_id": order.id,
                    "cluster_id": self.id,
                    "reason": "Could not allocate order items to nodes"
                }
            )

    def _is_in_range(self, location: Location) -> bool:
        """Check if a location is within the cluster's defined radius"""
        return self.center_location.distance_to(location) <= self.radius_miles

    def get_capabilities(self) -> Set[Capability]:
        """Get combined capabilities of all nodes"""
        return {cap for caps in self.node_capabilities.values() for cap in caps}

    async def allocate_order(self, order: Order) -> Optional[Dict[str, List[OrderItem]]]:
        """Attempt to allocate order items to nodes"""
        if not self.can_fulfill_order(order):
            return None

        allocation: Dict[str, List[OrderItem]] = {}
        remaining_items = list(order.items)
        reserved: Dict[str, int] = {}

        # Sort nodes by available capacity
        sorted_nodes = sorted(
            self.node_ids,
            key=lambda n: self.node_capacities.get(n, 0),
            reverse=True
        )

        for item in remaining_items:
            allocated = False
            for node_id in sorted_nodes:
                capabilities = self.node_capabilities.get(node_id, set())
                if (
                    item.product_type in capabilities and
                    self.node_capacities.get(node_id, 0) >= item.quantity
                ):
                    # Request capacity reservation
                    success = await self._request_capacity_reservation(
                        node_id, item.quantity
                    )
                    if success:
                        if node_id not in allocation:
                            allocation[node_id] = []
                        allocation[node_id].append(item)
                        reserved[node_id] = reserved.get(node_id, 0) + item.quantity
                        allocated = True
                        break

            if not allocated:
                # Rollback reservations
                for node_id, quantity in reserved.items():
                    await self._release_capacity_reservation(node_id, quantity)
                return None

        return allocation

    def can_fulfill_order(self, order: Order) -> bool:
        """Check if cluster can potentially fulfill order"""
        required_capabilities = {item.product_type for item in order.items}
        if not required_capabilities.issubset(self.get_capabilities()):
            return False

        total_items = sum(item.quantity for item in order.items)
        return total_items <= self.metrics.available_capacity

    async def _request_capacity_reservation(self, node_id: str, quantity: int) -> bool:
        """Request capacity reservation from node"""
        response = await self.transport.publish(
            f"node.{node_id}.reserve",
            {
                "quantity": quantity,
                "cluster_id": self.id
            }
        )
        return response and response.get("success", False)

    async def _release_capacity_reservation(self, node_id: str, quantity: int):
        """Release reserved capacity from node"""
        await self.transport.publish(
            f"node.{node_id}.release",
            {
                "quantity": quantity,
                "cluster_id": self.id
            }
        )

    def get_cluster_status(self) -> Dict:
        """Get cluster status summary"""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "node_count": len(self.node_ids),
            "capabilities": [cap.value for cap in self.get_capabilities()],
            "metrics": {
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "active_orders": self.metrics.active_orders,
                "total_orders_processed": self.metrics.total_orders_processed
            },
            "nodes": [
                {
                    "id": node_id,
                    "capabilities": [c.value for c in self.node_capabilities.get(node_id, set())],
                    "capacity": self.node_capacities.get(node_id, 0)
                }
                for node_id in self.node_ids
            ]
        }