from typing import List, Dict, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime

from ..models.shop import PrintShop, Location
from ..models.order import Order, OrderItem
from ..models.cluster import Cluster

logger = logging.getLogger(__name__)

@dataclass
class ShopScore:
    shop_id: str
    score: float
    distance: float
    capacity_score: float
    inventory_score: float
    details: Dict[str, float]

class RouteOptimizer:
    def __init__(self):
        # Scoring weights
        self.weights = {
            'distance': 0.4,      # Prefer closer shops
            'capacity': 0.3,      # Prefer shops with more capacity
            'inventory': 0.2,     # Prefer shops with inventory
            'capability': 0.1     # Prefer shops with all capabilities
        }
        
        # Maximum reasonable distance in miles
        self.max_distance = 500.0
        
    def score_shops(
        self, 
        order: Order, 
        available_shops: List[PrintShop]
    ) -> List[ShopScore]:
        """Score all available shops for an order"""
        scores = []
        
        for shop in available_shops:
            # Skip shops that definitely can't handle the order
            if not self._can_possibly_fulfill(shop, order):
                continue
                
            # Calculate individual scores
            distance_score = self._calculate_distance_score(
                shop.location, 
                order.customer_location
            )
            
            capacity_score = self._calculate_capacity_score(
                shop,
                order
            )
            
            inventory_score = self._calculate_inventory_score(
                shop,
                order
            )
            
            capability_score = self._calculate_capability_score(
                shop,
                order
            )
            
            # Calculate weighted total
            total_score = (
                self.weights['distance'] * distance_score +
                self.weights['capacity'] * capacity_score +
                self.weights['inventory'] * inventory_score +
                self.weights['capability'] * capability_score
            )
            
            if total_score > 0:
                scores.append(ShopScore(
                    shop_id=shop.id,
                    score=total_score,
                    distance=shop.location.distance_to(order.customer_location),
                    capacity_score=capacity_score,
                    inventory_score=inventory_score,
                    details={
                        'distance_score': distance_score,
                        'capacity_score': capacity_score,
                        'inventory_score': inventory_score,
                        'capability_score': capability_score
                    }
                ))
        
        # Sort by score descending
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores
    
    def optimize_cluster_assignment(
        self, 
        order: Order, 
        clusters: List[Cluster]
    ) -> Tuple[Cluster, float]:
        """Find the best cluster for an order"""
        best_cluster = None
        best_score = -1
        
        for cluster in clusters:
            # Skip clusters that definitely can't handle the order
            if not cluster.can_fulfill_order(order):
                continue
                
            # Score the cluster
            distance_score = self._calculate_distance_score(
                cluster.center_location,
                order.customer_location
            )
            
            capacity_score = sum(
                shop.current_capacity for shop in cluster.shops
            ) / max(1, len(cluster.shops))
            
            capability_score = len(
                set().union(*[shop.capabilities for shop in cluster.shops])
            ) / len(set(item.product_type for item in order.items))
            
            # Calculate weighted score
            score = (
                distance_score * 0.5 +
                capacity_score * 0.3 +
                capability_score * 0.2
            )
            
            if score > best_score:
                best_score = score
                best_cluster = cluster
        
        return best_cluster, best_score
    
    def _can_possibly_fulfill(self, shop: PrintShop, order: Order) -> bool:
        """Quick check if shop could possibly fulfill order"""
        # Check total capacity
        total_quantity = sum(item.quantity for item in order.items)
        if not shop.has_capacity(total_quantity):
            return False
            
        # Check capabilities
        required_capabilities = {item.product_type for item in order.items}
        if not required_capabilities.issubset(shop.capabilities):
            return False
            
        # Check distance
        if shop.location.distance_to(order.customer_location) > self.max_distance:
            return False
            
        return True
    
    def _calculate_distance_score(
        self,
        shop_location: Location,
        customer_location: Location
    ) -> float:
        """Calculate distance-based score (0-1)"""
        distance = shop_location.distance_to(customer_location)
        
        if distance > self.max_distance:
            return 0.0
            
        # Inverse distance scoring - closer is better
        return 1.0 - (distance / self.max_distance)
    
    def _calculate_capacity_score(
        self,
        shop: PrintShop,
        order: Order
    ) -> float:
        """Calculate capacity-based score (0-1)"""
        total_quantity = sum(item.quantity for item in order.items)
        
        if not shop.has_capacity(total_quantity):
            return 0.0
            
        # Score based on available capacity ratio
        return shop.current_capacity / shop.daily_capacity
    
    def _calculate_inventory_score(
        self,
        shop: PrintShop,
        order: Order
    ) -> float:
        """Calculate inventory-based score (0-1)"""
        if not order.items:
            return 1.0
            
        inventory_scores = []
        for item in order.items:
            if item.sku in shop.inventory:
                inventory_level = shop.inventory[item.sku].quantity
                if inventory_level >= item.quantity:
                    inventory_scores.append(1.0)
                else:
                    inventory_scores.append(inventory_level / item.quantity)
            else:
                inventory_scores.append(0.0)
                
        return sum(inventory_scores) / len(inventory_scores)
    
    def _calculate_capability_score(
        self,
        shop: PrintShop,
        order: Order
    ) -> float:
        """Calculate capability-based score (0-1)"""
        required_capabilities = {item.product_type for item in order.items}
        available_capabilities = shop.capabilities
        
        if not required_capabilities:
            return 1.0
            
        matching_capabilities = required_capabilities.intersection(available_capabilities)
        return len(matching_capabilities) / len(required_capabilities)