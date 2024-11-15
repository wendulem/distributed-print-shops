from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional
from datetime import datetime
import logging

from .shop import PrintShop, Location, Capability
from .order import Order, OrderItem

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
    """Represents a geographic cluster of print shops"""
    id: str
    center_location: Location
    radius_miles: float = 100.0  # Default cluster radius
    shops: Set[PrintShop] = field(default_factory=set)
    metrics: ClusterMetrics = field(default_factory=ClusterMetrics)
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_shop(self, shop: PrintShop) -> bool:
        """Add a shop to the cluster if within radius"""
        if self._is_in_range(shop.location):
            self.shops.add(shop)
            self.metrics.total_capacity += shop.daily_capacity
            self.metrics.available_capacity += shop.daily_capacity
            logger.info(f"Added shop {shop.id} to cluster {self.id}")
            return True
        return False
    
    def remove_shop(self, shop: PrintShop):
        """Remove a shop from the cluster"""
        if shop in self.shops:
            self.shops.remove(shop)
            self.metrics.total_capacity -= shop.daily_capacity
            self.metrics.available_capacity -= shop.daily_capacity
            logger.info(f"Removed shop {shop.id} from cluster {self.id}")
    
    def _is_in_range(self, location: Location) -> bool:
        """Check if a location is within cluster radius"""
        distance = self.center_location.distance_to(location)
        return distance <= self.radius_miles
    
    def get_capabilities(self) -> Set[Capability]:
        """Get combined capabilities of all shops in cluster"""
        return {cap for shop in self.shops for cap in shop.capabilities}
    
    def can_fulfill_order(self, order: Order) -> bool:
        """Check if cluster can fulfill an order"""
        required_capabilities = {item.product_type for item in order.items}
        cluster_capabilities = self.get_capabilities()
        
        # Check capabilities
        if not required_capabilities.issubset(cluster_capabilities):
            return False
            
        # Check capacity
        total_items = sum(item.quantity for item in order.items)
        return total_items <= self.metrics.available_capacity
    
    def allocate_order(self, order: Order) -> Optional[Dict[PrintShop, List[OrderItem]]]:
        """
        Attempt to allocate order items to shops in cluster.
        Returns mapping of shops to their allocated items, or None if unable to allocate.
        """
        if not self.can_fulfill_order(order):
            return None
            
        allocation: Dict[PrintShop, List[OrderItem]] = {}
        remaining_items = list(order.items)
        
        # Sort shops by available capacity (descending)
        sorted_shops = sorted(
            self.shops,
            key=lambda s: s.daily_capacity,
            reverse=True
        )
        
        # Try to allocate items to shops
        while remaining_items:
            item = remaining_items.pop(0)
            allocated = False
            
            for shop in sorted_shops:
                if (
                    item.product_type in shop.capabilities
                    and shop.daily_capacity >= item.quantity
                ):
                    if shop not in allocation:
                        allocation[shop] = []
                    allocation[shop].append(item)
                    shop.daily_capacity -= item.quantity
                    allocated = True
                    break
            
            if not allocated:
                # Rollback allocations
                for shop, items in allocation.items():
                    shop.daily_capacity += sum(item.quantity for item in items)
                return None
        
        # Update cluster metrics
        total_quantity = sum(
            item.quantity for items in allocation.values() for item in items
        )
        self.metrics.available_capacity -= total_quantity
        self.metrics.record_order()
        
        return allocation
    
    def get_status(self) -> Dict:
        """Get cluster status summary"""
        return {
            "id": self.id,
            "shop_count": len(self.shops),
            "capabilities": list(self.get_capabilities()),
            "metrics": {
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "active_orders": self.metrics.active_orders,
                "total_orders_processed": self.metrics.total_orders_processed
            },
            "shops": [
                {
                    "id": shop.id,
                    "location": {
                        "lat": shop.location.latitude,
                        "lon": shop.location.longitude
                    },
                    "capabilities": list(shop.capabilities),
                    "capacity": shop.daily_capacity
                }
                for shop in self.shops
            ]
        }