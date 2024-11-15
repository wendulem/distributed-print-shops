from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
import asyncio
import logging
from datetime import datetime
import json

from ..models.shop import PrintShop, ShopStatus, Location
from ..models.order import Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)

@dataclass
class NodeState:
    """Tracks runtime state of a node"""
    active_orders: Dict[str, Order] = field(default_factory=dict)
    neighbors: Dict[str, 'PrintShopNode'] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    order_history: List[str] = field(default_factory=list)
    production_queue: List[str] = field(default_factory=list)

class PrintShopNode:
    def __init__(self, shop: PrintShop):
        self.shop = shop
        self.state = NodeState()
        self.heartbeat_interval = 30  # seconds
        self.max_queue_size = 100
        self.max_neighbors = 10  # Limit number of direct neighbors

    async def start(self):
        """Start node operations"""
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._process_production_queue())
        logger.info(f"Node {self.shop.id} started")

    def add_neighbor(self, neighbor: 'PrintShopNode') -> bool:
        """Add a neighboring node"""
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
            # Check if we can handle the order
            if self._can_handle_order(order):
                # Add to production queue
                if len(self.state.production_queue) < self.max_queue_size:
                    self.state.production_queue.append(order.id)
                    self.state.active_orders[order.id] = order
                    order.add_status_update(
                        OrderStatus.ASSIGNED,
                        f"Assigned to shop {self.shop.id}"
                    )
                    logger.info(f"Node {self.shop.id} accepted order {order.id}")
                    return True
                
            # Try to forward to neighbors if we can't handle it
            return await self._forward_order(order)

        except Exception as e:
            logger.error(f"Error handling order {order.id}: {e}")
            return False

    def _can_handle_order(self, order: Order) -> bool:
        """Check if node can handle the order"""
        total_quantity = sum(item.quantity for item in order.items)
        
        # Check capacity
        if not self.shop.has_capacity(total_quantity):
            return False
            
        # Check capabilities and inventory
        for item in order.items:
            if not self.shop.can_fulfill_item(item.product_type, item.quantity):
                return False
                
        return True

    async def _forward_order(self, order: Order) -> bool:
        """Attempt to forward order to neighbors"""
        # Sort neighbors by distance to customer
        sorted_neighbors = sorted(
            self.state.neighbors.values(),
            key=lambda n: n.shop.location.distance_to(order.customer_location)
        )
        
        # Try each neighbor
        for neighbor in sorted_neighbors:
            try:
                if await neighbor.handle_order(order):
                    logger.info(
                        f"Node {self.shop.id} forwarded order {order.id} "
                        f"to neighbor {neighbor.shop.id}"
                    )
                    return True
            except Exception:
                continue
                
        return False

    async def _heartbeat_loop(self):
        """Periodic heartbeat to maintain node status"""
        while True:
            try:
                self.state.last_heartbeat = datetime.now()
                self.shop.last_heartbeat = datetime.now()
                
                # Check neighbor health
                unhealthy_neighbors = []
                for neighbor_id, neighbor in self.state.neighbors.items():
                    if not neighbor.is_healthy():
                        unhealthy_neighbors.append(neighbor_id)
                
                # Remove unhealthy neighbors
                for neighbor_id in unhealthy_neighbors:
                    self.remove_neighbor(neighbor_id)
                
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
                        
                        # Update shop state
                        self.state.production_queue.pop(0)
                        self.state.order_history.append(order_id)
                        del self.state.active_orders[order_id]
                        
                        logger.info(f"Node {self.shop.id} completed order {order_id}")
                
            except Exception as e:
                logger.error(f"Error processing production queue: {e}")
                
            await asyncio.sleep(5)  # Check queue every 5 seconds

    async def _produce_order(self, order: Order):
        """Simulate order production"""
        # Calculate production time based on order size and complexity
        production_time = order.estimated_production_time()
        
        # Update order status
        order.add_status_update(
            OrderStatus.IN_PRODUCTION,
            f"Production started at {self.shop.id}"
        )
        
        # Simulate production time (reduced for testing)
        await asyncio.sleep(min(production_time, 10))  # Cap at 10 seconds for testing
        
        # Update shop capacity
        total_quantity = sum(item.quantity for item in order.items)
        self.shop.release_capacity(total_quantity)

    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        return (
            self.shop.status == ShopStatus.ONLINE and
            (datetime.now() - self.state.last_heartbeat).total_seconds() < 60
        )

    def get_status(self) -> Dict:
        """Get node status summary"""
        return {
            "shop": self.shop.get_status_summary(),
            "state": {
                "active_orders": len(self.state.active_orders),
                "queue_size": len(self.state.production_queue),
                "neighbor_count": len(self.state.neighbors),
                "orders_completed": len(self.state.order_history),
                "last_heartbeat": self.state.last_heartbeat.isoformat()
            }
        }