from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import os

from api import configure_app
from src.network.discovery import NetworkDiscovery
from src.routing.router import OrderRouter
from src.models.shop import PrintShop, Location
from src.models.order import Order

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "development")
IS_PROD = ENV == "production"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global network, router, discovery
    logger.info(f"Starting application in {ENV} mode")

    # Initialize network
    discovery = await initialize_network()
    network = discovery.nodes
    router = OrderRouter(list(network.values()))

    yield

    # Shutdown
    logger.info("Shutting down application")

async def initialize_network() -> NetworkDiscovery:
    """Initialize the network discovery and management system"""
    discovery = NetworkDiscovery(
        initial_nodes=[
            PrintShop(
                id=os.getenv("NODE_ID"),
                url=os.getenv("NODE_URL"),
                location=Location(
                    latitude=float(os.getenv("LOCATION_LAT")),
                    longitude=float(os.getenv("LOCATION_LON"))
                ),
                daily_capacity=int(os.getenv("DAILY_CAPACITY")),
                capabilities=os.getenv("CAPABILITIES", "").split(",")
            )
        ]
    )
    await discovery.initialize()
    return discovery

async def startup_event():
    """Initialize network and start background tasks"""
    global network, router, discovery
    logger.info(f"Starting application in {ENV} mode")

    # Initialize network
    discovery = await initialize_network()
    network = discovery.nodes
    router = OrderRouter(list(network.values()))

    if not IS_PROD:
        # Local development: handle everything in one process
        await discovery.initialize()
        logger.info("Started background tasks for development mode")
    else:
        # Production: worker handles background tasks
        logger.info("Production mode: background tasks handled by worker")

async def shutdown_event():
    """Handle shutdown tasks"""
    pass

async def process_order(router: OrderRouter, order: Order):
    """Process a single order through the network"""
    try:
        assignment = await router.route_order(order)
        logger.info(f"Order {order.id} assigned to nodes: {assignment.node_assignments}")
    except Exception as e:
        logger.error(f"Failed to process order {order.id}: {e}")

def run_app():
    app = FastAPI(lifespan=lifespan)  # Create the FastAPI app instance
    configure_app(app)  # Pass the app instance to api.py for configuration
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