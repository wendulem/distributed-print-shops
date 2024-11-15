from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional
from enum import Enum
from datetime import datetime
import math

class Capability(Enum):
    TSHIRT = "t-shirt"
    HOODIE = "hoodie"
    MUG = "mug"
    BOTTLE = "bottle"
    STICKER = "sticker"
    POSTER = "poster"
    BUSINESS_CARD = "business-card"
    POSTCARD = "postcard"

class ShopStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    LIMITED = "limited"

@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    
    def distance_to(self, other: 'Location') -> float:
        """Calculate distance in miles using Haversine formula"""
        R = 3959.87433  # Earth's radius in miles

        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

@dataclass
class InventoryItem:
    sku: str
    quantity: int
    reorder_point: int
    max_quantity: int
    last_updated: datetime = field(default_factory=datetime.now)

    def needs_reorder(self) -> bool:
        return self.quantity <= self.reorder_point

    def space_available(self) -> int:
        return self.max_quantity - self.quantity

@dataclass
class PrintShop:
    id: str
    name: str
    location: Location
    capabilities: Set[Capability]
    daily_capacity: int
    
    # Runtime state
    status: ShopStatus = field(default=ShopStatus.ONLINE)
    current_capacity: int = field(init=False)
    inventory: Dict[str, InventoryItem] = field(default_factory=dict)
    active_orders: List[str] = field(default_factory=list)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.current_capacity = self.daily_capacity

    def __hash__(self):
        """Make PrintShop hashable based on its ID"""
        return hash(self.id)

    def __eq__(self, other):
        """PrintShops are equal if they have the same ID"""
        if not isinstance(other, PrintShop):
            return False
        return self.id == other.id

    def update_status(self, new_status: ShopStatus, reason: Optional[str] = None):
        """Update shop status and log the change"""
        old_status = self.status
        self.status = new_status
        self.last_heartbeat = datetime.now()
        
        # In a real implementation, you'd probably want to log this change
        return {
            "timestamp": self.last_heartbeat,
            "shop_id": self.id,
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason
        }

    def has_capacity(self, quantity: int) -> bool:
        """Check if shop can handle additional orders of given quantity"""
        return (
            self.status == ShopStatus.ONLINE and 
            self.current_capacity >= quantity
        )

    def reserve_capacity(self, quantity: int) -> bool:
        """Attempt to reserve capacity for an order"""
        if self.has_capacity(quantity):
            self.current_capacity -= quantity
            return True
        return False

    def release_capacity(self, quantity: int):
        """Release previously reserved capacity"""
        self.current_capacity = min(
            self.daily_capacity,
            self.current_capacity + quantity
        )

    def update_inventory(self, sku: str, quantity: int):
        """Update inventory levels for a SKU"""
        if sku in self.inventory:
            item = self.inventory[sku]
            item.quantity = quantity
            item.last_updated = datetime.now()
        else:
            # Default reorder point and max quantity - in practice, these would be SKU-specific
            self.inventory[sku] = InventoryItem(
                sku=sku,
                quantity=quantity,
                reorder_point=50,
                max_quantity=1000
            )

    def can_fulfill_item(self, product_type: Capability, quantity: int, sku: Optional[str] = None) -> bool:
        """Check if shop can fulfill a specific item"""
        if product_type not in self.capabilities:
            return False
            
        if not self.has_capacity(quantity):
            return False
            
        if sku and sku in self.inventory:
            return self.inventory[sku].quantity >= quantity
            
        return True

    def get_low_inventory_items(self) -> List[InventoryItem]:
        """Get list of items that need reordering"""
        return [
            item for item in self.inventory.values()
            if item.needs_reorder()
        ]

    def get_status_summary(self) -> dict:
        """Get summary of shop status"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "location": {
                "lat": self.location.latitude,
                "lon": self.location.longitude
            },
            "capabilities": [cap.value for cap in self.capabilities],
            "capacity": {
                "daily": self.daily_capacity,
                "available": self.current_capacity,
                "utilization": (self.daily_capacity - self.current_capacity) / self.daily_capacity
            },
            "active_orders": len(self.active_orders),
            "inventory_status": {
                "total_skus": len(self.inventory),
                "low_stock_items": len(self.get_low_inventory_items())
            },
            "last_heartbeat": self.last_heartbeat.isoformat()
        }

    def is_healthy(self, max_heartbeat_age_seconds: int = 300) -> bool:
        """Check if shop is healthy and responsive"""
        if self.status == ShopStatus.OFFLINE:
            return False
            
        heartbeat_age = (datetime.now() - self.last_heartbeat).total_seconds()
        return heartbeat_age <= max_heartbeat_age_seconds