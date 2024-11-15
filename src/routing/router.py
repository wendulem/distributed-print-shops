from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging
import asyncio
from datetime import datetime

from ..models.order import Order, OrderStatus
from ..models.shop import PrintShop
from ..models.cluster import Cluster
from .optimizer import RouteOptimizer, ShopScore

logger = logging.getLogger(__name__)

@dataclass
class RoutingResult:
    success: bool
    order_id: str
    node_assignments: Dict[str, List[int]]  # shop_id -> list of item indices
    estimated_time: float
    details: Dict[str, any]

class OrderRouter:
    def __init__(self, nodes: List[PrintShop], clusters: Optional[List[Cluster]] = None):
        self.nodes = {node.id: node for node in nodes}
        self.clusters = clusters or []
        self.optimizer = RouteOptimizer()
        
        # Routing statistics
        self.total_orders = 0
        self.successful_routes = 0
        self.failed_routes = 0
        
        # Configuration
        self.max_routing_attempts = 3
        self.max_split_shops = 3  # Maximum number of shops to split an order across

    async def route_order(self, order: Order) -> RoutingResult:
        """Route an order to appropriate print shop(s)"""
        try:
            self.total_orders += 1
            
            # First try cluster-based routing
            if self.clusters:
                result = await self._try_cluster_routing(order)
                if result and result.success:
                    self.successful_routes += 1
                    return result
            
            # Fall back to direct shop routing
            result = await self._try_direct_routing(order)
            if result and result.success:
                self.successful_routes += 1
                return result
            
            # If both fail, try split routing
            result = await self._try_split_routing(order)
            if result and result.success:
                self.successful_routes += 1
                return result
            
            # If all routing attempts fail
            self.failed_routes += 1
            return RoutingResult(
                success=False,
                order_id=order.id,
                node_assignments={},
                estimated_time=0,
                details={"error": "No viable routing solution found"}
            )
            
        except Exception as e:
            logger.error(f"Error routing order {order.id}: {e}")
            self.failed_routes += 1
            return RoutingResult(
                success=False,
                order_id=order.id,
                node_assignments={},
                estimated_time=0,
                details={"error": str(e)}
            )

    async def _try_cluster_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to route order through a cluster"""
        best_cluster, score = self.optimizer.optimize_cluster_assignment(
            order, 
            self.clusters
        )
        
        if best_cluster and score > 0:
            # Try to allocate within cluster
            allocation = best_cluster.allocate_order(order)
            if allocation:
                assignments = {
                    shop.id: [
                        i for i, item in enumerate(order.items)
                        if item in items
                    ]
                    for shop, items in allocation.items()
                }
                
                estimated_time = order.estimated_production_time()
                
                return RoutingResult(
                    success=True,
                    order_id=order.id,
                    node_assignments=assignments,
                    estimated_time=estimated_time,
                    details={
                        "routing_type": "cluster",
                        "cluster_id": best_cluster.id,
                        "cluster_score": score
                    }
                )
        
        return None

    async def _try_direct_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to route entire order to a single shop"""
        available_shops = list(self.nodes.values())
        shop_scores = self.optimizer.score_shops(order, available_shops)
        
        for shop_score in shop_scores:
            shop = self.nodes[shop_score.shop_id]
            if shop.can_fulfill_item(order.items[0].product_type, order.items[0].quantity):
                return RoutingResult(
                    success=True,
                    order_id=order.id,
                    node_assignments={shop.id: list(range(len(order.items)))},
                    estimated_time=order.estimated_production_time(),
                    details={
                        "routing_type": "direct",
                        "shop_score": shop_score.details
                    }
                )
        
        return None

    async def _try_split_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to split order across multiple shops"""
        available_shops = list(self.nodes.values())
        unassigned_items = list(range(len(order.items)))
        assignments: Dict[str, List[int]] = {}
        
        while unassigned_items:
            # Create a temporary order with remaining items
            remaining_order = Order(
                id=order.id,
                customer_location=order.customer_location,
                items=[order.items[i] for i in unassigned_items]
            )
            
            # Score shops for remaining items
            shop_scores = self.optimizer.score_shops(
                remaining_order,
                available_shops
            )
            
            assigned = False
            for shop_score in shop_scores:
                shop = self.nodes[shop_score.shop_id]
                
                # Find items this shop can handle
                assignable_items = []
                for item_idx in unassigned_items:
                    item = order.items[item_idx]
                    if shop.can_fulfill_item(item.product_type, item.quantity):
                        assignable_items.append(item_idx)
                
                if assignable_items:
                    assignments[shop.id] = assignable_items
                    for idx in assignable_items:
                        unassigned_items.remove(idx)
                    assigned = True
                    break
            
            if not assigned or len(assignments) >= self.max_split_shops:
                return None
        
        if not unassigned_items:
            return RoutingResult(
                success=True,
                order_id=order.id,
                node_assignments=assignments,
                estimated_time=order.estimated_production_time() * 1.2,  # Add 20% for split handling
                details={
                    "routing_type": "split",
                    "shop_count": len(assignments)
                }
            )
        
        return None

    def get_routing_stats(self) -> Dict:
        """Get current routing statistics"""
        return {
            "total_orders": self.total_orders,
            "successful_routes": self.successful_routes,
            "failed_routes": self.failed_routes,
            "success_rate": (
                self.successful_routes / self.total_orders 
                if self.total_orders > 0 else 0
            )
        }

    async def rebalance_assignments(self) -> Dict:
        """Periodically rebalance assignments to optimize network"""
        rebalanced = 0
        total_checked = 0
        
        # Implementation would check current assignments and rebalance if beneficial
        # This is a placeholder for future implementation
        
        return {
            "orders_checked": total_checked,
            "orders_rebalanced": rebalanced
        }