import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List

from src.models.shop import PrintShop, Location, Capability, ShopStatus
from src.models.order import Order, OrderItem, OrderStatus, OrderPriority
from src.models.cluster import Cluster, ClusterMetrics
from src.network.discovery import NetworkDiscovery
from src.network.node import PrintShopNode
from src.routing.router import OrderRouter
from src.network.protocol import NetworkProtocol

@pytest.fixture
async def setup_network():
    """Set up a complete test network with multiple regions"""
    # Create shops across different regions
    shops = [
        # SF Bay Area
        PrintShop(
            id="sf-1",
            name="SF Print Co",
            location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        ),
        PrintShop(
            id="oak-1",
            name="Oakland Prints",
            location=Location(37.8044, -122.2712),
            capabilities={Capability.TSHIRT, Capability.MUG},
            daily_capacity=80
        ),
        # Los Angeles
        PrintShop(
            id="la-1",
            name="LA Prints",
            location=Location(34.0522, -118.2437),
            capabilities={Capability.TSHIRT, Capability.BOTTLE},
            daily_capacity=150
        ),
        PrintShop(
            id="la-2",
            name="LA Custom",
            location=Location(34.0549, -118.2426),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=120
        ),
        # New York
        PrintShop(
            id="ny-1",
            name="NYC Prints",
            location=Location(40.7128, -74.0060),
            capabilities={Capability.TSHIRT, Capability.POSTER},
            daily_capacity=200
        ),
    ]
    
    # Initialize network
    discovery = NetworkDiscovery()
    nodes = []
    
    for shop in shops:
        node = PrintShopNode(shop)
        node.protocol = NetworkProtocol(shop.id)
        await node.start()
        nodes.append(node)
        discovery.add_node(node)
    
    await discovery.initialize()
    
    router = OrderRouter(nodes, list(discovery.clusters.values()))
    
    return {
        "discovery": discovery,
        "router": router,
        "nodes": nodes
    }

@pytest.mark.asyncio
async def test_complete_order_flow(setup_network):
    """Test complete order flow from submission to completion"""
    network = await setup_network
    
    # Create test order in SF
    order = Order(
        id="test-order-1",
        customer_location=Location(37.7749, -122.4194),  # SF location
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
    
    # Route order
    result = await network["router"].route_order(order)
    assert result.success, "Order should be routed successfully"
    assert result.node_assignments, "Order should be assigned to nodes"
    
    # Verify order assignments
    for shop_id, item_indices in result.node_assignments.items():
        node = next(n for n in network["nodes"] if n.shop.id == shop_id)
        assert order.id in node.state.active_orders, f"Order should be assigned to {shop_id}"

    # Wait for order processing
    await asyncio.sleep(1)  # Simulated processing time
    
    # Verify order completion
    for shop_id in result.node_assignments:
        node = next(n for n in network["nodes"] if n.shop.id == shop_id)
        assert order.id in node.state.order_history, f"Order should be completed by {shop_id}"

@pytest.mark.asyncio
async def test_network_resilience(setup_network):
    """Test system handling of node failures"""
    network = await setup_network
    
    # Create order
    order = Order(
        id="test-order-2",
        customer_location=Location(37.7749, -122.4194),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=40,
                design_url="https://example.com/design3"
            )
        ]
    )
    
    # Simulate node failure
    sf_node = next(n for n in network["nodes"] if n.shop.id == "sf-1")
    sf_node.shop.status = ShopStatus.OFFLINE
    
    # Route order
    result = await network["router"].route_order(order)
    assert result.success, "Order should be routed despite node failure"
    
    # Verify order wasn't assigned to failed node
    assert "sf-1" not in result.node_assignments, "Failed node should not receive orders"

@pytest.mark.asyncio
async def test_load_balancing(setup_network):
    """Test system load balancing under heavy order volume"""
    network = await setup_network
    
    # Create multiple orders
    orders = []
    for i in range(10):
        orders.append(Order(
            id=f"load-test-{i}",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=20,
                    design_url=f"https://example.com/design-{i}"
                )
            ]
        ))
    
    # Route all orders
    results = await asyncio.gather(*[
        network["router"].route_order(order)
        for order in orders
    ])
    
    # Verify all orders were routed
    assert all(r.success for r in results), "All orders should be routed"
    
    # Check load distribution
    node_loads = {}
    for result in results:
        for shop_id in result.node_assignments:
            node_loads[shop_id] = node_loads.get(shop_id, 0) + 1
    
    # Verify reasonable load distribution
    load_std_dev = calculate_std_dev(node_loads.values())
    assert load_std_dev < len(orders) / 2, "Load should be reasonably balanced"

@pytest.mark.asyncio
async def test_geographic_routing(setup_network):
    """Test geographic routing preferences"""
    network = await setup_network
    
    # Create orders in different regions
    sf_order = Order(
        id="sf-order",
        customer_location=Location(37.7749, -122.4194),  # SF
        items=[OrderItem(product_type=Capability.TSHIRT.value, quantity=30,
               design_url="https://example.com/design-sf")]
    )
    
    la_order = Order(
        id="la-order",
        customer_location=Location(34.0522, -118.2437),  # LA
        items=[OrderItem(product_type=Capability.TSHIRT.value, quantity=30,
               design_url="https://example.com/design-la")]
    )
    
    # Route orders
    sf_result = await network["router"].route_order(sf_order)
    la_result = await network["router"].route_order(la_order)
    
    # Verify geographic preference
    assert any(shop_id.startswith("sf") or shop_id.startswith("oak") 
              for shop_id in sf_result.node_assignments), \
        "SF order should be routed to Bay Area"
    
    assert any(shop_id.startswith("la") 
              for shop_id in la_result.node_assignments), \
        "LA order should be routed to LA"

def calculate_std_dev(values):
    """Helper function to calculate standard deviation"""
    if not values:
        return 0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5

@pytest.mark.asyncio
async def test_capacity_limits(setup_network):
    """Test system behavior at capacity limits"""
    network = await setup_network
    
    # Create large order that exceeds single shop capacity
    large_order = Order(
        id="large-order",
        customer_location=Location(37.7749, -122.4194),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=250,  # Larger than any single shop capacity
                design_url="https://example.com/design-large"
            )
        ]
    )
    
    # Route order
    result = await network["router"].route_order(large_order)
    assert result.success, "Large order should be routed"
    assert len(result.node_assignments) > 1, "Large order should be split across shops"

@pytest.mark.asyncio
async def test_system_recovery(setup_network):
    """Test system recovery after node failures"""
    network = await setup_network
    
    # Simulate multiple node failures
    failed_nodes = network["nodes"][:2]
    for node in failed_nodes:
        node.shop.status = ShopStatus.OFFLINE
    
    # Create order
    order = Order(
        id="recovery-test",
        customer_location=Location(37.7749, -122.4194),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=30,
                design_url="https://example.com/design-recovery"
            )
        ]
    )
    
    # Route order
    result = await network["router"].route_order(order)
    assert result.success, "Order should be routed despite failures"
    
    # Simulate recovery
    for node in failed_nodes:
        node.shop.status = ShopStatus.ONLINE
    
    # Verify system includes recovered nodes in routing
    new_order = Order(
        id="recovery-test-2",
        customer_location=Location(37.7749, -122.4194),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT.value,
                quantity=30,
                design_url="https://example.com/design-recovery2"
            )
        ]
    )
    
    result = await network["router"].route_order(new_order)
    assert any(node.shop.id in result.node_assignments for node in failed_nodes), \
        "Recovered nodes should be included in routing"