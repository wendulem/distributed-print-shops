from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import os

from .api import configure_app
from .network.discovery import NetworkDiscovery
from .routing.router import OrderRouter
from .models.shop import PrintShop, Location
from .models.node import PrintShopNode
from .models.cluster import Cluster
from .models.order import Order
from .protocol import NetworkProtocol

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "development")
IS_PROD = ENV == "production"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global discovery, router
    logger.info(f"Starting application in {ENV} mode")

    # Initialize the network discovery and related components
    discovery, router = await initialize_system()

    yield

    # Shutdown
    logger.info("Shutting down application")

async def initialize_system():
    """
    Initialize the entire system:
    - Create static PrintShop and corresponding runtime PrintShopNode.
    - Create a Cluster and add the node.
    - Initialize NetworkDiscovery with clusters.
    - Create an OrderRouter that uses cluster-based logic.
    """
    # Create static PrintShop model
    shop = PrintShop(
        id=os.getenv("NODE_ID", "default_node"),
        name=os.getenv("SHOP_NAME", "Default Shop"),
        location=Location(
            latitude=float(os.getenv("LOCATION_LAT", "0.0")),
            longitude=float(os.getenv("LOCATION_LON", "0.0"))
        ),
        capabilities=set(os.getenv("CAPABILITIES", "").split(",")),
        daily_capacity=int(os.getenv("DAILY_CAPACITY", "100"))
    )

    # Create runtime node (PrintShopNode)
    # The PrintShopNode manages capacity, inventory, status, and handles incoming orders at runtime
    node = PrintShopNode(shop=shop)

    # Create a Cluster and add this node
    cluster_id = "cluster-1"
    cluster = Cluster(
        id=cluster_id,
        center_location=shop.location,
        radius_miles=100.0
    )
    cluster.add_node(node)

    # Initialize NetworkDiscovery with this cluster
    discovery = NetworkDiscovery(initial_clusters=[cluster])
    await discovery.initialize()

    # Create OrderRouter with clusters and nodes
    # Extract nodes from the cluster(s)
    all_nodes = []
    for c in discovery.clusters.values():
        all_nodes.extend(list(c.nodes))

    router = OrderRouter(nodes=all_nodes, clusters=list(discovery.clusters.values()))

    return discovery, router

async def startup_event():
    """Initialize system and possibly start background tasks"""
    global discovery, router
    logger.info(f"Starting application in {ENV} mode")

    discovery, router = await initialize_system()

    # Additional startup logic if needed
    if not IS_PROD:
        logger.info("Development mode: background tasks run in the same process")
    else:
        logger.info("Production mode: background tasks handled separately")

async def shutdown_event():
    """Handle shutdown tasks if necessary"""
    logger.info("Application shutting down")

async def process_order(order: Order):
    """Process a single order through the system using the router"""
    global router
    if not router:
        logger.error("Router not initialized")
        return
    try:
        assignment = await router.route_order(order)
        if assignment.success:
            logger.info(f"Order {order.id} assigned to nodes: {assignment.node_assignments}")
        else:
            logger.warning(f"Order {order.id} could not be assigned: {assignment.details}")
    except Exception as e:
        logger.error(f"Failed to process order {order.id}: {e}")

def run_app():
    app = FastAPI(lifespan=lifespan)
    configure_app(app)  # Configure API endpoints, including cluster-level queries, etc.
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event)

    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )

if __name__ == "__main__":
    run_app()
