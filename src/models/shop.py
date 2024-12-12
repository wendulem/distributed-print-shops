from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional
from enum import Enum
from datetime import datetime
import math
from .location import Location

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
