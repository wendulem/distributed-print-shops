from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import os

from .api import configure_app
from .network.discovery import NetworkDiscovery
from .routing.router import OrderRouter
from .models.shop import PrintShop, Location
from .network.node import PrintShopNode
from .models.order import Order
from .infrastructure.messaging.memory import InMemoryMessageTransport
from .infrastructure.state.memory import InMemoryStateStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "development")
IS_PROD = ENV == "production"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global discovery, router, transport, state_store
    logger.info(f"Starting application in {ENV} mode")

    # Initialize infrastructure and system components
    transport, state_store, discovery, router = await initialize_system()

    yield

    # Shutdown
    logger.info("Shutting down application")

async def initialize_system():
    """
    Initialize the system with messaging infrastructure:
    1. Create messaging and state infrastructure
    2. Initialize network discovery
    3. Create and start nodes
    4. Initialize router
    """
    # Initialize infrastructure
    transport = InMemoryMessageTransport()
    state_store = InMemoryStateStore()
    
    # Initialize network discovery first
    discovery = NetworkDiscovery(transport)
    await discovery.start()

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

    # Create and start node
    node = PrintShopNode(
        shop=shop,
        message_transport=transport
    )
    await node.start()

    # Create router with messaging transport
    router = OrderRouter(message_transport=transport)

    # In production, we'd initialize Redis/Kafka here
    if IS_PROD:
        logger.info("Production mode: would initialize Redis/Kafka here")
        # TODO: Replace memory implementations with distributed ones
        # transport = KafkaMessageTransport(...)
        # state_store = RedisStateStore(...)

    return transport, state_store, discovery, router

async def startup_event():
    """Initialize system and start background tasks"""
    global discovery, router, transport, state_store
    logger.info(f"Starting application in {ENV} mode")

    transport, state_store, discovery, router = await initialize_system()

    if not IS_PROD:
        logger.info("Development mode: using in-memory transport and state store")
    else:
        logger.info("Production mode: using distributed transport and state store")

async def shutdown_event():
    """Handle graceful shutdown"""
    logger.info("Application shutting down")
    # TODO: Implement graceful shutdown of transport and state store

async def process_order(order: Order):
    """Process order through message-based routing"""
    try:
        # Publish order to the routing system
        await transport.publish("order.new", {
            "order": order.to_dict()
        })
        logger.info(f"Order {order.id} submitted for routing")
    except Exception as e:
        logger.error(f"Failed to process order {order.id}: {e}")

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(lifespan=lifespan)
    configure_app(app)
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event)
    return app

def run_app():
    """Run the application using uvicorn"""
    app = create_app()
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )

if __name__ == "__main__":
    run_app()