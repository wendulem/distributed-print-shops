from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional
from datetime import datetime
import logging

from .shop import PrintShop, Location, Capability
from .order import Order, OrderItem
from .node import PrintShopNode  # Assuming we have a node module with PrintShopNode
from .protocol import MessageType  # Assuming protocol.py defines message types

logger = logging.getLogger(__name__)

@dataclass
class ClusterMetrics:
    """Tracks operational metrics for a cluster"""
    total_capacity: int = 0
    available_capacity: int = 0
    active_orders: int = 0
    total_orders_processed: int = 0

    def update_capacity(self, delta: int):
        """Adjust the available capacity by a delta (can be positive or negative)."""
        self.available_capacity += delta

    def record_order(self):
        """Record a newly allocated order."""
        self.active_orders += 1
        self.total_orders_processed += 1

    def complete_order(self):
        """Mark an order as completed and free up an active slot."""
        self.active_orders -= 1


@dataclass
class Cluster:
    """
    Represents a geographic cluster of PrintShopNodes.

    A cluster groups multiple PrintShopNodes based on geographical proximity.
    Responsibilities include:
    - Cluster formation (adding/removing nodes)
    - Cluster-level order routing and allocation
    - Maintaining aggregate metrics and capabilities
    - Handling cluster-level messages (e.g. from discovery or other clusters)
    """
    id: str
    center_location: Location
    radius_miles: float = 100.0  # Default cluster radius
    nodes: Set[PrintShopNode] = field(default_factory=set)
    metrics: ClusterMetrics = field(default_factory=ClusterMetrics)
    created_at: datetime = field(default_factory=datetime.now)

    def add_node(self, node: PrintShopNode) -> bool:
        """
        Add a PrintShopNode to the cluster if it falls within the cluster's geographic radius.
        Updates cluster capacity metrics based on the node's shop daily capacity.
        """
        if self._is_in_range(node.shop.location):
            self.nodes.add(node)
            # The total and available capacity are based on sum of all nodes' daily capacities.
            # Here, we assume daily_capacity as a static maximum capacity reference.
            # Actual available capacity is checked at runtime via node.has_capacity().
            self.metrics.total_capacity += node.shop.daily_capacity
            self.metrics.available_capacity += node.shop.daily_capacity
            logger.info(f"Added node {node.shop.id} to cluster {self.id}")
            return True
        return False

    def remove_node(self, node: PrintShopNode):
        """Remove a PrintShopNode from the cluster."""
        if node in self.nodes:
            self.nodes.remove(node)
            self.metrics.total_capacity -= node.shop.daily_capacity
            self.metrics.available_capacity -= node.shop.daily_capacity
            logger.info(f"Removed node {node.shop.id} from cluster {self.id}")

    def _is_in_range(self, location: Location) -> bool:
        """Check if a location is within the cluster's defined radius."""
        distance = self.center_location.distance_to(location)
        return distance <= self.radius_miles

    def get_capabilities(self) -> Set[Capability]:
        """Get the combined capabilities of all nodes' shops in the cluster."""
        return {cap for node in self.nodes for cap in node.shop.capabilities}

    def can_fulfill_order(self, order: Order) -> bool:
        """
        Check if the cluster can fulfill an order by ensuring:
        - The cluster has all required capabilities.
        - The sum of all nodes' available capacity is enough for the order.
        """
        required_capabilities = {item.product_type for item in order.items}
        cluster_capabilities = self.get_capabilities()

        # Check capabilities
        if not required_capabilities.issubset(cluster_capabilities):
            return False

        # Check capacity among nodes
        total_items = sum(item.quantity for item in order.items)
        # Just because the cluster has a nominal available capacity doesn't guarantee
        # actual runtime availability. We must check if nodes collectively can handle it.
        # We'll do a more detailed allocation attempt in route_order.
        # Here we only check a rough threshold against cluster's recorded available_capacity.
        if total_items > self.metrics.available_capacity:
            return False

        # A more accurate check will be performed in route_order/allocate_order
        return True

    def route_order(self, order: Order) -> Optional[Dict[PrintShopNode, List[OrderItem]]]:
        """
        Attempt to route the order at the cluster level:
        - Check if the cluster can potentially fulfill the order.
        - If so, try to allocate the order items to nodes within the cluster.
        - Return the allocation mapping or None if unable to allocate.
        """
        if not self.can_fulfill_order(order):
            logger.debug(f"Cluster {self.id} cannot fulfill order {order.id}")
            return None
        return self.allocate_order(order)

    def allocate_order(self, order: Order) -> Optional[Dict[PrintShopNode, List[OrderItem]]]:
        """
        Attempt to allocate order items to nodes within the cluster.
        This method assumes that can_fulfill_order() has already been checked.

        Allocation strategy:
        1. Sort nodes by their current capacity (checked via node.has_capacity()) or daily capacity as fallback.
        2. For each order item, find the first node that can fulfill that item (can_fulfill_item() and reserve_capacity()).
        3. If any item cannot be allocated, roll back reservations.
        4. If successful, update cluster metrics and return the allocation mapping.
        """
        allocation: Dict[PrintShopNode, List[OrderItem]] = {}
        remaining_items = list(order.items)

        # Sort nodes by their runtime available capacity (descending).
        # We'll check runtime capacity node by node.
        # Since we don't have direct node available capacity field,
        # we rely on the node's has_capacity() method with a large hypothetical number to get a rough ordering.
        # In a complete system, nodes might provide a direct capacity metric.
        # We'll assume daily_capacity as a proxy sort order, then rely on actual checks in allocation.
        sorted_nodes = sorted(
            self.nodes,
            key=lambda n: n.shop.daily_capacity,
            reverse=True
        )

        # Store reserved capacity to allow rollback if allocation fails.
        reserved_capacities: Dict[PrintShopNode, int] = {}

        while remaining_items:
            item = remaining_items.pop(0)
            allocated = False

            for node in sorted_nodes:
                # Check if the node can fulfill this particular item
                if node.can_fulfill_item(item.product_type, item.quantity, sku=item.sku):
                    # Try to reserve capacity on this node
                    if node.reserve_capacity(item.quantity):
                        # We'll mark this allocation
                        if node not in allocation:
                            allocation[node] = []
                        allocation[node].append(item)
                        reserved_capacities[node] = reserved_capacities.get(node, 0) + item.quantity
                        allocated = True
                        break

            if not allocated:
                # Rollback reservations
                for n, qty in reserved_capacities.items():
                    n.release_capacity(qty)
                logger.debug(f"Cluster {self.id} failed to allocate order {order.id}, rolling back.")
                return None

        # If we reach here, all items have been allocated successfully
        # Update cluster metrics
        total_quantity = sum(i.quantity for items in allocation.values() for i in items)
        self.metrics.available_capacity -= total_quantity
        self.metrics.record_order()

        # Finally, instruct nodes to fulfill the items (simulate production)
        # This step would trigger the nodes' internal logic to process the orders
        # e.g., node.fulfill_items(allocation[node]) could start production asynchronously.
        for node, items in allocation.items():
            # Let's assume we have a method fulfill_items(items: List[OrderItem]) on the node
            node.fulfill_items(items)

        logger.info(f"Cluster {self.id} allocated order {order.id}")
        return allocation

    def get_cluster_status(self) -> Dict:
        """Get a status summary of the cluster."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "node_count": len(self.nodes),
            "capabilities": [cap.value for cap in self.get_capabilities()],
            "metrics": {
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "active_orders": self.metrics.active_orders,
                "total_orders_processed": self.metrics.total_orders_processed
            },
            "nodes": [
                {
                    "id": node.shop.id,
                    "location": {
                        "lat": node.shop.location.latitude,
                        "lon": node.shop.location.longitude
                    },
                    "capabilities": [c.value for c in node.shop.capabilities],
                    "capacity": node.shop.daily_capacity,
                    # Optionally, we could include runtime info from the node if exposed
                }
                for node in self.nodes
            ]
        }

    def handle_cluster_message(self, message: dict, source_id: Optional[str] = None):
        """
        Handle intra-cluster communication and coordination messages.
        This could be messages from other clusters, cluster managers, or discovery services.
        
        For example:
        - CLUSTER_UPDATE: Update metrics or redistribute load
        - CLUSTER_JOIN/LEAVE: Adjust cluster membership
        - ORDER_ROUTING: Requests to route orders
        """
        msg_type = message.get("type")

        if msg_type == MessageType.CLUSTER_JOIN:
            # Handle logic for a node requesting to join (not implemented here)
            pass
        elif msg_type == MessageType.CLUSTER_LEAVE:
            # Handle logic for a node leaving the cluster (not implemented here)
            pass
        elif msg_type == MessageType.CLUSTER_UPDATE:
            # Possibly update metrics, re-balance capacities, etc.
            pass
        else:
            logger.debug(f"Cluster {self.id} received unknown message type: {msg_type}")
