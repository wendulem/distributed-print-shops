from typing import List
import asyncio
import logging
from datetime import datetime

from .models.shop import PrintShop, Location, Capability
from .models.order import Order, OrderItem
from .network.node import PrintShopNode
from .network.discovery import NetworkDiscovery
from .routing.router import OrderRouter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def initialize_network() -> List[PrintShopNode]:
    """Initialize a test network of print shops"""
    # Create some sample print shops
    shops = [
        PrintShop(
            id="sf-shop-1",
            name="SF Print Co",
            location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        ),
        PrintShop(
            id="la-shop-1",
            name="LA Prints",
            location=Location(34.0522, -118.2437),
            capabilities={Capability.TSHIRT, Capability.MUG},
            daily_capacity=150
        ),
        PrintShop(
            id="ny-shop-1",
            name="NYC Printing",
            location=Location(40.7128, -74.0060),
            capabilities={Capability.TSHIRT, Capability.BOTTLE},
            daily_capacity=200
        )
    ]
    
    # Create network nodes for each shop
    # nodes = [PrintShopNode(shop) for shop in shops]
    
    # Initialize network discovery
    # network = NetworkDiscovery(nodes)
    network = NetworkDiscovery(shops)
    await network.initialize()
    
    # return nodes
    return network

async def process_order(router: OrderRouter, order: Order):
    """Process a single order through the network"""
    try:
        assignment = await router.route_order(order)
        logger.info(f"Order {order.id} assigned to nodes: {assignment.node_assignments}")
    except Exception as e:
        logger.error(f"Failed to process order {order.id}: {e}")

async def main():
    # Initialize the network
    logger.info("Initializing print shop network...")
    nodes = await initialize_network()
    
    # Create router
    router = OrderRouter(nodes)
    
    # Create some test orders
    test_orders = [
        Order(
            id="order-1",
            customer_location=Location(37.7749, -122.4194),  # SF
            items=[
                OrderItem(
                    product_type="TSHIRT",
                    quantity=50,
                    design_url="https://designs.example.com/design1"
                )
            ],
            created_at=datetime.now()
        ),
        Order(
            id="order-2",
            customer_location=Location(34.0522, -118.2437),  # LA
            items=[
                OrderItem(
                    product_type="MUG",
                    quantity=25,
                    design_url="https://designs.example.com/design2"
                )
            ],
            created_at=datetime.now()
        )
    ]
    
    # Process test orders
    logger.info("Processing test orders...")
    await asyncio.gather(*[
        process_order(router, order) 
        for order in test_orders
    ])
    
    # Print network state
    logger.info("\nFinal Network State:")
    for node in nodes:
        logger.info(f"\nNode {node.shop.id}:")
        logger.info(f"  Location: {node.shop.location}")
        logger.info(f"  Remaining Capacity: {node.shop.daily_capacity}")
        logger.info(f"  Connected to: {[n.shop.id for n in node.neighbors]}")
        logger.info(f"  Active Orders: {len(node.assigned_orders)}")

def run():
    """Entry point for the application"""
    asyncio.run(main())

if __name__ == "__main__":
    run()