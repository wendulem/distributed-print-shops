import pytest
from datetime import datetime, timedelta

from src.models.shop import PrintShop, Location, Capability, ShopStatus, InventoryItem
from src.models.order import Order, OrderItem, OrderStatus, OrderPriority
from src.models.cluster import Cluster, ClusterMetrics

class TestLocation:
    def test_distance_calculation(self):
        """Test geographic distance calculations"""
        sf = Location(37.7749, -122.4194)  # San Francisco
        ny = Location(40.7128, -74.0060)   # New York
        la = Location(34.0522, -118.2437)  # Los Angeles
        
        # Test known distances (approximate)
        assert abs(sf.distance_to(ny) - 2570) < 50, "SF-NY distance should be ~2570 miles"
        assert abs(sf.distance_to(la) - 350) < 20, "SF-LA distance should be ~350 miles"
        
        # Test symmetry
        assert abs(sf.distance_to(ny) - ny.distance_to(sf)) < 0.1, \
            "Distance should be symmetrical"
        
        # Test zero distance to self
        assert sf.distance_to(sf) == 0, "Distance to self should be 0"


class TestPrintShop:
    @pytest.fixture
    def shop(self):
        return PrintShop(
            id="test-shop",
            name="Test Print Shop",
            location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        )

    def test_shop_initialization(self, shop):
        """Test print shop initialization"""
        assert shop.id == "test-shop"
        assert shop.status == ShopStatus.ONLINE
        assert shop.current_capacity == shop.daily_capacity
        assert len(shop.capabilities) == 2

    def test_capacity_management(self, shop):
        """Test capacity reservation and release"""
        assert shop.has_capacity(50)
        assert shop.reserve_capacity(50)
        assert shop.current_capacity == 50
        
        # Test over-capacity
        assert not shop.has_capacity(60)
        assert not shop.reserve_capacity(60)
        
        # Test release
        shop.release_capacity(20)
        assert shop.current_capacity == 70
        
        # Test max capacity constraint
        shop.release_capacity(500)
        assert shop.current_capacity == shop.daily_capacity

    def test_inventory_management(self, shop):
        """Test inventory tracking"""
        # Add inventory
        shop.update_inventory("TSHIRT-M-WHITE", 100)
        assert "TSHIRT-M-WHITE" in shop.inventory
        assert shop.inventory["TSHIRT-M-WHITE"].quantity == 100
        
        # Update inventory
        shop.update_inventory("TSHIRT-M-WHITE", 80)
        assert shop.inventory["TSHIRT-M-WHITE"].quantity == 80
        
        # Check low inventory
        low_items = shop.get_low_inventory_items()
        assert isinstance(low_items, list)
        
        # Test can_fulfill_item
        assert shop.can_fulfill_item(
            Capability.TSHIRT,
            50,
            "TSHIRT-M-WHITE"
        )

    def test_health_checking(self, shop):
        """Test shop health monitoring"""
        assert shop.is_healthy()
        
        # Test unhealthy conditions
        shop.status = ShopStatus.OFFLINE
        assert not shop.is_healthy()
        
        shop.status = ShopStatus.ONLINE
        shop.last_heartbeat = datetime.now() - timedelta(minutes=10)
        assert not shop.is_healthy(max_heartbeat_age_seconds=300)


class TestOrder:
    @pytest.fixture
    def order(self):
        return Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                ),
                OrderItem(
                    product_type=Capability.HOODIE.value,
                    quantity=30,
                    design_url="https://example.com/design2"
                )
            ],
            priority=OrderPriority.NORMAL
        )

    def test_order_initialization(self, order):
        """Test order initialization"""
        assert order.id == "test-order"
        assert len(order.items) == 2
        assert order.status == OrderStatus.CREATED
        assert order.priority == OrderPriority.NORMAL

    def test_order_status_updates(self, order):
        """Test order status management"""
        order.add_status_update(
            OrderStatus.ASSIGNED,
            "Assigned to shop"
        )
        assert order.status == OrderStatus.ASSIGNED
        assert len(order.status_history) == 1
        
        # Test status history
        last_update = order.status_history[-1]
        assert last_update["status"] == OrderStatus.ASSIGNED
        assert last_update["message"] == "Assigned to shop"

    def test_shop_assignment(self, order):
        """Test order assignment to shops"""
        order.assign_to_shop("shop-1", [0])  # Assign first item
        assert "shop-1" in order.shop_assignments
        assert order.items[0].assigned_shop_id == "shop-1"
        
        # Test assignment status
        assert not order.is_fully_assigned()
        order.assign_to_shop("shop-2", [1])  # Assign second item
        assert order.is_fully_assigned()
        
        # Test unassigned items
        unassigned = order.get_unassigned_items()
        assert len(unassigned) == 0

    def test_production_time_estimation(self, order):
        """Test production time calculations"""
        normal_time = order.estimated_production_time()
        
        # Test priority impact
        order.priority = OrderPriority.RUSH
        rush_time = order.estimated_production_time()
        assert rush_time < normal_time
        
        order.priority = OrderPriority.LOW
        low_time = order.estimated_production_time()
        assert low_time > normal_time


class TestCluster:
    @pytest.fixture
    def cluster(self):
        return Cluster(
            id="test-cluster",
            center_location=Location(37.7749, -122.4194),
            radius_miles=100.0
        )

    @pytest.fixture
    def shop(self):
        return PrintShop(
            id="test-shop",
            name="Test Shop",
            location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        )

    def test_cluster_initialization(self, cluster):
        """Test cluster initialization"""
        assert cluster.id == "test-cluster"
        assert cluster.radius_miles == 100.0
        assert len(cluster.shops) == 0
        assert isinstance(cluster.metrics, ClusterMetrics)

    def test_shop_management(self, cluster, shop):
        """Test adding/removing shops"""
        # Add shop
        assert cluster.add_shop(shop)
        assert shop in cluster.shops
        assert cluster.metrics.total_capacity == shop.daily_capacity
        
        # Remove shop
        cluster.remove_shop(shop)
        assert shop not in cluster.shops
        assert cluster.metrics.total_capacity == 0

    def test_order_fulfillment(self, cluster, shop):
        """Test order fulfillment capabilities"""
        cluster.add_shop(shop)
        
        order = Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        # Test fulfillment check
        assert cluster.can_fulfill_order(order)
        
        # Test allocation
        allocation = cluster.allocate_order(order)
        assert allocation is not None
        assert shop in allocation
        assert cluster.metrics.available_capacity == shop.daily_capacity - 50

    def test_cluster_metrics(self, cluster, shop):
        """Test cluster metrics tracking"""
        cluster.add_shop(shop)
        
        # Test initial metrics
        assert cluster.metrics.total_capacity == shop.daily_capacity
        assert cluster.metrics.active_orders == 0
        
        # Test metrics updates
        cluster.metrics.record_order()
        assert cluster.metrics.active_orders == 1
        assert cluster.metrics.total_orders_processed == 1
        
        cluster.metrics.complete_order()
        assert cluster.metrics.active_orders == 0