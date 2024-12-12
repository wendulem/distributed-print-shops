import asyncio
import logging
from src.infrastructure.messaging.memory import InMemoryMessageTransport
from src.infrastructure.state.memory import InMemoryStateStore
from src.network.discovery import NetworkDiscovery
from src.models.shop import PrintShop, Capability
from src.models.location import Location
from src.network.node import PrintShopNode
from src.models.order import Order, OrderItem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_basic_system():
    logging.info("Starting test...")
    
    # Initialize infrastructure
    transport = InMemoryMessageTransport()
    state_store = InMemoryStateStore()
    
    logging.info("Infrastructure initialized.")
    
    # Start network discovery
    discovery = NetworkDiscovery(transport)
    await discovery.start()
    
    logging.info("Network discovery started.")
    
    customer_and_shop_location = Location(latitude=40.7128, longitude=-74.0060)
    
    # Create and start a node
    shop = PrintShop(
        id="test_shop_1",
        name="Test Shop",
        location=customer_and_shop_location,
        capabilities={Capability.TSHIRT, Capability.HOODIE},
        daily_capacity=100
    )
    
    node = PrintShopNode(shop=shop, message_transport=transport)
    await node.start()
    
    # Create a test order
    order = Order(
        id="test_order_1",
        customer_location=customer_and_shop_location,
        items=[
            OrderItem(
                product_type=Capability.TSHIRT,
                quantity=5,
                sku="TSHIRT-001",
                design_url="https://i.imgur.com/ITa8Pg7.png"
            )
        ]
    )
    
    # Submit order and wait for processing
    await transport.publish("order.new", {
        "order": order.get_summary()
    })
    
    logging.info("Test order submitted.")
    
    # Wait a bit to see messages flow
    await asyncio.sleep(5)
    
    logging.info("Test completed.")

if __name__ == "__main__":
    asyncio.run(test_basic_system())