import pytest
import asyncio
from datetime import datetime

from src.models.shop import PrintShop, Location, Capability, ShopStatus
from src.models.order import Order, OrderItem, OrderStatus
from src.models.cluster import Cluster, ClusterMetrics
from src.network.discovery import NetworkDiscovery
from src.network.node import PrintShopNode
from src.routing.router import OrderRouter

@pytest.fixture
def sample_shops():
    """Create a set of test print shops"""
    return [
        PrintShop(
            id="sf-1",
            name="SF Print Co",
            location=Location(37.7749, -122.4194),  # San Francisco
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        ),
        PrintShop(
            id="sf-2",
            name="SF Custom Prints",
            location=Location(37.7858, -122.4064),  # Near SF
            capabilities={Capability.TSHIRT, Capability.MUG},
            daily_capacity=150
        ),
        PrintShop(
            id="la-1",
            name="LA Prints",
            location=Location(34.0522, -118.2437),  # Los Angeles
            capabilities={Capability.TSHIRT, Capability.BOTTLE},
            daily_capacity=200
        )
    ]

@pytest.fixture
def network_discovery(sample_shops):
    """Initialize NetworkDiscovery with sample shops"""
    discovery = NetworkDiscovery()
    for shop in sample_shops:
        discovery.add_node(PrintShopNode(shop))
    return discovery

@pytest.fixture
def sample_order():
    """Create a test order"""
    return Order(
        id="test-order-1",
        customer_location=Location(37.7749, -122.4194),  # SF location
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=50,
                design_url="https://example.com/design1"
            )
        ]
    )

@pytest.mark.asyncio
async def test_cluster_formation(network_discovery):
    """Test that clusters are formed based on geographic proximity"""
    # Initialize network
    await network_discovery.initialize()
    
    # Check cluster formation
    assert len(network_discovery.clusters) > 0, "Clusters should be formed"
    
    # Verify SF shops are in same cluster
    sf_cluster = None
    for cluster in network_discovery.clusters.values():
        if any(shop.id.startswith("sf") for shop in cluster.shops):
            sf_cluster = cluster
            break
    
    assert sf_cluster is not None, "Should find cluster with SF shops"
    assert len([s for s in sf_cluster.shops if s.id.startswith("sf")]) == 2, \
        "SF shops should be in same cluster"

@pytest.mark.asyncio
async def test_cluster_order_handling(network_discovery, sample_order):
    """Test that clusters can handle orders appropriately"""
    await network_discovery.initialize()
    
    # Get cluster for order location
    cluster = network_discovery.find_cluster_for_location(sample_order.customer_location)
    assert cluster is not None, "Should find appropriate cluster"
    
    # Verify cluster can handle order
    can_fulfill = cluster.can_fulfill_order(sample_order)
    assert can_fulfill, "Cluster should be able to fulfill order"
    
    # Try to allocate order
    allocation = cluster.allocate_order(sample_order)
    assert allocation is not None, "Should successfully allocate order"
    assert len(allocation) >= 1, "Should assign to at least one shop"

@pytest.mark.asyncio
async def test_cluster_capacity_management(network_discovery, sample_order):
    """Test cluster capacity management"""
    await network_discovery.initialize()
    cluster = network_discovery.find_cluster_for_location(sample_order.customer_location)
    
    # Record initial capacity
    initial_capacity = cluster.metrics.available_capacity
    
    # Allocate order
    allocation = cluster.allocate_order(sample_order)
    assert allocation is not None
    
    # Verify capacity was reduced
    assert cluster.metrics.available_capacity < initial_capacity, \
        "Capacity should be reduced after allocation"
    
    # Verify by exact amount
    total_quantity = sum(item.quantity for item in sample_order.items)
    expected_capacity = initial_capacity - total_quantity
    assert cluster.metrics.available_capacity == expected_capacity, \
        "Capacity should be reduced by exact order quantity"

@pytest.mark.asyncio
async def test_cluster_shop_failure(network_discovery, sample_order):
    """Test cluster behavior when a shop fails"""
    await network_discovery.initialize()
    cluster = network_discovery.find_cluster_for_location(sample_order.customer_location)
    
    # Record initial state
    initial_shop_count = len(cluster.shops)
    initial_capacity = cluster.metrics.total_capacity
    
    # Simulate shop failure
    first_shop = next(iter(cluster.shops))
    first_shop.status = ShopStatus.OFFLINE
    
    # Verify cluster adapts
    assert cluster.can_fulfill_order(sample_order), \
        "Cluster should still handle orders with one shop down"
    
    # Verify metrics updated
    assert cluster.metrics.total_capacity < initial_capacity, \
        "Cluster capacity should be reduced when shop fails"

@pytest.mark.asyncio
async def test_cross_cluster_coordination(network_discovery, sample_order):
    """Test coordination between clusters when one is at capacity"""
    await network_discovery.initialize()
    
    # Get primary cluster
    primary_cluster = network_discovery.find_cluster_for_location(
        sample_order.customer_location
    )
    
    # Fill primary cluster capacity
    big_order = Order(
        id="big-order",
        customer_location=sample_order.customer_location,
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=primary_cluster.metrics.available_capacity,
                design_url="https://example.com/design2"
            )
        ]
    )
    
    # Allocate big order to fill capacity
    primary_cluster.allocate_order(big_order)
    
    # Try to route new order
    router = OrderRouter(list(network_discovery.nodes.values()), 
                        list(network_discovery.clusters.values()))
    result = await router.route_order(sample_order)
    
    # Verify order was routed successfully, even if to another cluster
    assert result.success, "Order should be routed despite primary cluster being full"

def test_cluster_metrics(network_discovery):
    """Test cluster metrics tracking"""
    # Get a cluster
    cluster = next(iter(network_discovery.clusters.values()))
    
    # Verify metrics initialization
    assert cluster.metrics.total_capacity > 0, "Should have total capacity"
    assert cluster.metrics.available_capacity > 0, "Should have available capacity"
    assert cluster.metrics.active_orders == 0, "Should start with no orders"
    
    # Verify metrics calculations
    expected_capacity = sum(shop.daily_capacity for shop in cluster.shops)
    assert cluster.metrics.total_capacity == expected_capacity, \
        "Total capacity should match sum of shop capacities"