from typing import List, Dict, Optional
from dataclasses import dataclass
import logging
import asyncio
from datetime import datetime

from ..models.order import Order, OrderStatus
from ..models.cluster import Cluster
from ..models.node import PrintShopNode  # Assuming we have a node.py providing PrintShopNode
from .optimizer import RouteOptimizer, ShopScore

logger = logging.getLogger(__name__)

@dataclass
class RoutingResult:
    success: bool
    order_id: str
    node_assignments: Dict[str, List[int]]  # node_id -> list of item indices
    estimated_time: float
    details: Dict[str, any]

class OrderRouter:
    """
    Routes orders to appropriate clusters or nodes based on location, capabilities, and capacity.
    Tries cluster-level routing first, then falls back to direct node routing, and finally attempts
    splitting orders across multiple nodes or even multiple clusters if needed.
    """
    def __init__(
        self, 
        nodes: List[PrintShopNode],
        clusters: Optional[List[Cluster]] = None
    ):
        # Map of node_id to PrintShopNode, providing runtime checks
        self.nodes = {node.shop.id: node for node in nodes}
        self.clusters = clusters or []
        self.optimizer = RouteOptimizer()
        
        # Routing statistics
        self.total_orders = 0
        self.successful_routes = 0
        self.failed_routes = 0
        
        # Configuration
        self.max_routing_attempts = 3
        self.max_split_shops = 3  # Maximum number of nodes to split an order across
        self.max_split_clusters = 2  # Maximum number of clusters to split an order across

    async def route_order(self, order: Order) -> RoutingResult:
        """Route an order to appropriate cluster(s) or nodes."""
        self.total_orders += 1

        try:
            # 1. Try cluster-based routing
            if self.clusters:
                result = await self._try_cluster_routing(order)
                if result and result.success:
                    self.successful_routes += 1
                    return result
            
            # 2. If no suitable cluster found, try routing directly to a single node
            result = await self._try_direct_node_routing(order)
            if result and result.success:
                self.successful_routes += 1
                return result
            
            # 3. Try splitting the order across multiple nodes
            result = await self._try_split_node_routing(order)
            if result and result.success:
                self.successful_routes += 1
                return result
            
            # 4. As a last resort, try splitting across multiple clusters (if we have more than one)
            if len(self.clusters) > 1:
                result = await self._try_multi_cluster_routing(order)
                if result and result.success:
                    self.successful_routes += 1
                    return result
            
            # If all attempts fail
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
        """Attempt to route order through the best-scoring cluster."""
        best_cluster, score = self.optimizer.optimize_cluster_assignment(order, self.clusters)
        
        if best_cluster and score > 0:
            # Attempt cluster-level routing
            allocation = best_cluster.route_order(order)
            if allocation:
                # allocation is a Dict[PrintShopNode, List[OrderItem]]
                assignments = self._build_assignments_from_allocation(order, allocation)
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

    async def _try_direct_node_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to route entire order to a single node (PrintShopNode)."""
        available_nodes = list(self.nodes.values())
        node_scores = self.optimizer.score_nodes(order, available_nodes)
        
        # Sort nodes by score, try the best one first
        for node_score in node_scores:
            node = self.nodes[node_score.node_id]
            total_quantity = sum(item.quantity for item in order.items)
            if node.can_fulfill_entire_order(order) and node.reserve_capacity(total_quantity):
                # Assign entire order to this node
                assignments = {node.shop.id: list(range(len(order.items)))}
                estimated_time = order.estimated_production_time()
                return RoutingResult(
                    success=True,
                    order_id=order.id,
                    node_assignments=assignments,
                    estimated_time=estimated_time,
                    details={
                        "routing_type": "direct_node",
                        "node_id": node.shop.id,
                        "node_score": node_score.details
                    }
                )
        
        return None

    async def _try_split_node_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to split the order across multiple nodes."""
        available_nodes = list(self.nodes.values())
        unassigned_items = list(range(len(order.items)))
        assignments: Dict[str, List[int]] = {}
        
        while unassigned_items:
            remaining_items = [order.items[i] for i in unassigned_items]
            remaining_quantity = sum(item.quantity for item in remaining_items)
            
            # Score nodes for the remaining items
            node_scores = self.optimizer.score_nodes(
                order,
                available_nodes
            )
            
            assigned = False
            for node_score in node_scores:
                node = self.nodes[node_score.node_id]
                
                # Find which items this node can fulfill
                fulfillable_indices = []
                for i in unassigned_items:
                    item = order.items[i]
                    if node.can_fulfill_item(item.product_type, item.quantity):
                        fulfillable_indices.append(i)
                
                if fulfillable_indices:
                    # Reserve capacity for these items if possible
                    qty_to_reserve = sum(order.items[i].quantity for i in fulfillable_indices)
                    if node.reserve_capacity(qty_to_reserve):
                        assignments[node.shop.id] = fulfillable_indices
                        for idx in fulfillable_indices:
                            unassigned_items.remove(idx)
                        assigned = True
                        break
            
            if not assigned or len(assignments) >= self.max_split_shops:
                return None
        
        if not unassigned_items:
            # Add a time penalty for split routing
            estimated_time = order.estimated_production_time() * 1.2
            return RoutingResult(
                success=True,
                order_id=order.id,
                node_assignments=assignments,
                estimated_time=estimated_time,
                details={
                    "routing_type": "split_node",
                    "node_count": len(assignments)
                }
            )
        
        return None

    async def _try_multi_cluster_routing(self, order: Order) -> Optional[RoutingResult]:
        """Attempt to split the order across multiple clusters if one cluster can't handle it alone."""
        if len(self.clusters) < 2:
            return None
        
        # Sort clusters by proximity or score
        cluster_scores = self.optimizer.score_clusters(order, self.clusters)
        
        # Attempt splitting items across clusters
        unassigned_items = list(range(len(order.items)))
        assignments: Dict[str, List[int]] = {}
        
        for cluster_score in cluster_scores:
            cluster = cluster_score.cluster
            if not unassigned_items:
                break
            
            # Create a partial order with remaining items
            partial_order = Order(
                id=order.id,
                customer_location=order.customer_location,
                items=[order.items[i] for i in unassigned_items]
            )
            
            allocation = cluster.route_order(partial_order)
            if allocation:
                cluster_assignments = self._build_assignments_from_allocation(partial_order, allocation)
                
                # Map partial_order items back to original order indices
                rem_map = {partial_order.items[i]: unassigned_items[i] for i in range(len(unassigned_items))}
                
                for node_id, item_indices in cluster_assignments.items():
                    real_indices = [rem_map[partial_order.items[i]] for i in item_indices]
                    assignments[node_id] = real_indices
                
                # Remove assigned items from unassigned
                for idx_set in assignments.values():
                    for idx in idx_set:
                        if idx in unassigned_items:
                            unassigned_items.remove(idx)
                
                if len(assignments) >= self.max_split_clusters:
                    break
        
        if not unassigned_items:
            estimated_time = order.estimated_production_time() * 1.3  # More penalty for multi-cluster
            return RoutingResult(
                success=True,
                order_id=order.id,
                node_assignments=assignments,
                estimated_time=estimated_time,
                details={
                    "routing_type": "multi_cluster",
                    "cluster_count": len(self.clusters),
                    "assigned_clusters": len(assignments)
                }
            )
        
        return None

    def _build_assignments_from_allocation(self, order: Order, allocation: Dict['PrintShopNode', List['OrderItem']]) -> Dict[str, List[int]]:
        """Build a node_assignments map from a cluster allocation result."""
        assignments = {}
        for node, items in allocation.items():
            indices = [i for i, order_item in enumerate(order.items) if order_item in items]
            assignments[node.shop.id] = indices
        return assignments

    def get_routing_stats(self) -> Dict:
        """Get current routing statistics."""
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
        """Periodically rebalance assignments to optimize network usage (placeholder)."""
        rebalanced = 0
        total_checked = 0
        # Future logic: analyze current order assignments and redistribute if beneficial
        return {
            "orders_checked": total_checked,
            "orders_rebalanced": rebalanced
        }
