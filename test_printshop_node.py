import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from src.models.shop import PrintShop, ShopStatus, Capability, InventoryItem
from src.models.order import Order, OrderItem
from src.models.location import Location
from src.network.node import PrintShopNode
from src.infrastructure.messaging.memory import InMemoryMessageTransport
from src.infrastructure.messaging.types import MessageTypes

@pytest.fixture
def print_shop():
    return PrintShop(
        id="test_shop",
        name="Test Shop",
        location=Location(latitude=40.7128, longitude=-74.0060),
        capabilities={Capability.TSHIRT, Capability.HOODIE},
        daily_capacity=100
    )

@pytest.fixture
def message_transport():
    return InMemoryMessageTransport()

@pytest.fixture
async def print_shop_node(print_shop, message_transport):
    async with PrintShopNode(shop=print_shop, message_transport=message_transport) as node:
        yield node

@pytest.mark.asyncio
async def test_start(print_shop_node):
    node = await anext(print_shop_node)
    
    assert node.state.status == ShopStatus.ONLINE
    assert node.state.current_capacity == node.shop.daily_capacity

# Verifies that the node publishes the correct join request when joining a cluster.
@pytest.mark.asyncio
async def test_join_cluster(print_shop_node, message_transport):
    node = await anext(print_shop_node)
    
    cluster_id = "test_cluster"
    await node.join_cluster(cluster_id)
    assert message_transport.published_messages["cluster.test_cluster.join"][-1]["node_id"] == node.shop.id

# Checks that the node's status is set to OFFLINE and the correct "bye" message is published when stopping the node.
@pytest.mark.asyncio
async def test_stop(print_shop_node, message_transport):
    node = await anext(print_shop_node)
    
    await node.stop()
    assert node.state.status == ShopStatus.OFFLINE
    assert message_transport.published_messages["node.bye"][-1]["shop_id"] == node.shop.id
    
@pytest.mark.asyncio
async def test_can_handle_order(print_shop_node):
    node = await anext(print_shop_node)
    
    order_supported = Order(
        id="test_order_supported",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=5,
                sku="TSHIRT-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    order_unsupported = Order(
        id="test_order_unsupported",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.MUG,
                quantity=5,
                sku="MUG-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    assert node._can_handle_order(order_supported) is True
    assert node._can_handle_order(order_unsupported) is False

@pytest.mark.asyncio
async def test_handle_order_success(print_shop_node):
    node = await anext(print_shop_node)
    
    order = Order(
        id="test_order",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=5,
                sku="TSHIRT-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    result = await node.handle_order(order)
    assert result is True
    assert order.id in node.state.active_orders
    assert order.id in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity - 5

# Tests the scenario where the node receives an order that exceeds its daily capacity. It verifies that the order is not accepted and the capacity remains unchanged.
@pytest.mark.asyncio
async def test_handle_order_insufficient_capacity(print_shop_node):
    node = await anext(print_shop_node)
    
    order = Order(
        id="test_order",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=200,
                sku="TSHIRT-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    result = await node.handle_order(order)
    assert result is False
    assert order.id not in node.state.active_orders
    assert order.id not in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity

# Tests the scenario where the node receives an order with an unsupported product type. It ensures that the order is not accepted and the capacity remains unchanged.
@pytest.mark.asyncio
async def test_handle_order_unsupported_product(print_shop_node):
    node = await anext(print_shop_node)
    
    order = Order(
        id="test_order",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.MUG,
                quantity=5,
                sku="MUG-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    result = await node.handle_order(order)
    assert result is False
    assert order.id not in node.state.active_orders
    assert order.id not in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity

# Verifies that the node can handle multiple orders and correctly updates its capacity and order queues.
@pytest.mark.asyncio
async def test_handle_multiple_orders(print_shop_node):
    node = await anext(print_shop_node)
    
    order1 = Order(
        id="test_order_1",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=10,
                sku="TSHIRT-001",
                design_url="https://example.com/design1.png"
            )
        ]
    )
    order2 = Order(
        id="test_order_2",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.HOODIE,
                quantity=5,
                sku="HOODIE-001",
                design_url="https://example.com/design2.png"
            )
        ]
    )
    await node.handle_order(order1)
    await node.handle_order(order2)
    assert order1.id in node.state.active_orders
    assert order1.id in node.state.production_queue
    assert order2.id in node.state.active_orders
    assert order2.id in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity - 15

# Tests the processing of the production queue by simulating the completion of orders and verifying that the orders are moved to the order history and the capacity is released.
@pytest.mark.asyncio
async def test_process_production_queue(print_shop_node, message_transport):
    node = await anext(print_shop_node)
    
    order1 = Order(
        id="test_order_1",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=10,
                sku="TSHIRT-001",
                design_url="https://example.com/design1.png"
            )
        ]
    )
    order2 = Order(
        id="test_order_2",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.HOODIE,
                quantity=5,
                sku="HOODIE-001",
                design_url="https://example.com/design2.png"
            )
        ]
    )
    await node.handle_order(order1)
    await node.handle_order(order2)
    await asyncio.sleep(11)  # Wait for production to complete
    assert order1.id not in node.state.active_orders
    assert order1.id not in node.state.production_queue
    assert order1.id in node.state.order_history
    assert order2.id not in node.state.active_orders
    assert order2.id not in node.state.production_queue
    assert order2.id in node.state.order_history
    assert node.state.current_capacity == node.shop.daily_capacity

# Checks that the node goes offline if it doesn't receive a heartbeat within a specified time interval.
@pytest.mark.asyncio
async def test_node_offline_without_heartbeat(print_shop_node):
    node = await anext(print_shop_node)
    
    node.heartbeat_interval = 1
    node.state.last_heartbeat = datetime.now() - timedelta(seconds=300)
    await asyncio.sleep(2)  # Wait for heartbeat loop to run
    assert node.state.status == ShopStatus.OFFLINE

# test_update_inventory(): Verifies that the node can update its inventory correctly.
# test_handle_inventory_query(): Tests the handling of an inventory query by verifying that the correct inventory update message is published.
# test_handle_inventory_update(): Checks that the node can handle an inventory update message and update its inventory accordingly.

@pytest.mark.asyncio
async def test_update_inventory(print_shop_node):
    node = await anext(print_shop_node)
    
    node.update_inventory("TSHIRT-001", 100)
    assert "TSHIRT-001" in node.state.inventory
    assert node.state.inventory["TSHIRT-001"].quantity == 100
    node.update_inventory("TSHIRT-001", 50)
    assert node.state.inventory["TSHIRT-001"].quantity == 50

@pytest.mark.asyncio
async def test_handle_inventory_query(print_shop_node, message_transport):
    node = await anext(print_shop_node)
    
    node.update_inventory("TSHIRT-001", 100)
    await node._handle_inventory_query({"sku": "TSHIRT-001"})
    assert message_transport.published_messages[MessageTypes.INVENTORY_UPDATE][-1]["data"]["quantity"] == 100

@pytest.mark.asyncio
async def test_handle_inventory_update(print_shop_node):
    node = await anext(print_shop_node)
    
    await node._handle_inventory_update({"sku": "HOODIE-001", "quantity": 50})
    assert "HOODIE-001" in node.state.inventory
    assert node.state.inventory["HOODIE-001"].quantity == 50
    
# additional edge cases

@pytest.mark.asyncio
async def test_handle_order_multiple_items(print_shop_node):
    node = await anext(print_shop_node)
    
    order = Order(
        id="test_order_multiple_items",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=5,
                sku="TSHIRT-001",
                design_url="https://example.com/design1.png"
            ),
            OrderItem(
                product_type=Capability.HOODIE,
                quantity=3,
                sku="HOODIE-001",
                design_url="https://example.com/design2.png"
            )
        ]
    )
    result = await node.handle_order(order)
    assert result is True
    assert order.id in node.state.active_orders
    assert order.id in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity - 8

@pytest.mark.asyncio
async def test_handle_order_insufficient_inventory(print_shop_node):
    node = await anext(print_shop_node)
    
    node.update_inventory("TSHIRT-001", 2)
    order = Order(
        id="test_order_insufficient_inventory",
        customer_location=Location(latitude=40.7128, longitude=-74.0060),
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=5,
                sku="TSHIRT-001",
                design_url="https://example.com/design.png"
            )
        ]
    )
    result = await node.handle_order(order)
    assert result is False
    assert order.id not in node.state.active_orders
    assert order.id not in node.state.production_queue
    assert node.state.current_capacity == node.shop.daily_capacity