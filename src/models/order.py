from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field

class OrderStatus(Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"
    FAILED = "failed"

class OrderPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    RUSH = "rush"

@dataclass
class Location:
    latitude: float
    longitude: float

class OrderItem(BaseModel):
    """Individual item within an order"""
    product_type: str
    quantity: int = Field(gt=0)  # Ensure quantity is positive
    design_url: str
    sku: Optional[str] = None
    notes: Optional[str] = None
    
    # Production details
    assigned_shop_id: Optional[str] = None
    production_status: str = "pending"
    
    class Config:
        frozen = True  # Make the model immutable

class Order(BaseModel):
    """Represents a customer order for printed products"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    customer_location: Location
    items: List[OrderItem]
    
    # Order metadata
    created_at: datetime = Field(default_factory=datetime.now)
    status: OrderStatus = Field(default=OrderStatus.CREATED)
    priority: OrderPriority = Field(default=OrderPriority.NORMAL)
    
    # Delivery requirements
    required_by: Optional[datetime] = None
    shipping_speed: str = "standard"
    
    # Tracking
    assigned_cluster_id: Optional[str] = None
    shop_assignments: dict = Field(default_factory=dict)  # shop_id -> [item_ids]
    latest_update: datetime = Field(default_factory=datetime.now)
    status_history: List[dict] = Field(default_factory=list)
    
    def add_status_update(self, new_status: OrderStatus, message: Optional[str] = None):
        """Record a status change in the order's history"""
        update = {
            "timestamp": datetime.now(),
            "status": new_status,
            "message": message
        }
        self.status_history.append(update)
        self.status = new_status
        self.latest_update = update["timestamp"]
    
    def assign_to_shop(self, shop_id: str, item_indices: List[int]):
        """Assign specific items to a print shop"""
        self.shop_assignments[shop_id] = item_indices
        for idx in item_indices:
            if idx < len(self.items):
                self.items[idx].assigned_shop_id = shop_id
                self.items[idx].production_status = "assigned"
    
    def is_fully_assigned(self) -> bool:
        """Check if all items have been assigned to shops"""
        return all(item.assigned_shop_id is not None for item in self.items)
    
    def get_unassigned_items(self) -> List[tuple[int, OrderItem]]:
        """Get items that haven't been assigned to a shop"""
        return [(i, item) for i, item in enumerate(self.items) 
                if item.assigned_shop_id is None]
    
    def estimated_production_time(self) -> float:
        """Estimate total production time in hours"""
        base_time = 24.0  # Base production time in hours
        
        # Adjust based on priority
        priority_multipliers = {
            OrderPriority.LOW: 1.5,
            OrderPriority.NORMAL: 1.0,
            OrderPriority.HIGH: 0.75,
            OrderPriority.RUSH: 0.5
        }
        
        total_items = sum(item.quantity for item in self.items)
        time_estimate = base_time * priority_multipliers[self.priority]
        
        # Add time for large orders
        if total_items > 100:
            time_estimate *= 1.5
        
        return time_estimate
    
    def get_summary(self) -> dict:
        """Get a summary of the order status"""
        return {
            "id": self.id,
            "status": self.status.value,
            "priority": self.priority.value,
            "item_count": len(self.items),
            "total_quantity": sum(item.quantity for item in self.items),
            "assigned_shops": list(self.shop_assignments.keys()),
            "created_at": self.created_at.isoformat(),
            "latest_update": self.latest_update.isoformat(),
            "estimated_production_time": self.estimated_production_time(),
            "is_fully_assigned": self.is_fully_assigned()
        }
    
    class Config:
        """Pydantic configuration"""
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            OrderStatus: lambda v: v.value,
            OrderPriority: lambda v: v.value
        }