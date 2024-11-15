from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import os
import argparse
from typing import Optional
from contextlib import asynccontextmanager

from src.main import initialize_network, process_order
from src.models.order import Order
from src.routing.router import OrderRouter
from src.network.discovery import NetworkDiscovery

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "development")
IS_PROD = ENV == "production"

# Shared state
network = None
router = None
discovery = None

# Replace on_event with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global network, router, discovery
    logger.info(f"Starting application in {ENV} mode")
    
    # Initialize network - discovery is the network now
    discovery = await initialize_network()
    network = discovery.nodes
    router = OrderRouter(list(network.values()))
    
    if not IS_PROD:
        logger.info("Started background tasks for development mode")
    else:
        logger.info("Production mode: background tasks handled by worker")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")

app = FastAPI(lifespan=lifespan)

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize network and start background tasks"""
    global network, router, discovery
    
    logger.info(f"Starting application in {ENV} mode")
    
    # Initialize network
    nodes = await initialize_network()
    network = nodes
    router = OrderRouter(nodes)
    
    if not IS_PROD:
        # Local development: handle everything in one process
        discovery = NetworkDiscovery(nodes)
        await discovery.initialize()
        asyncio.create_task(periodic_health_check())
        logger.info("Started background tasks for development mode")
    else:
        # Production: worker handles background tasks
        logger.info("Production mode: background tasks handled by worker")

async def periodic_health_check():
    """Background task for health checking in development"""
    while True:
        try:
            if discovery:
                await discovery._periodic_health_check()
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Health check error: {e}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "node_count": len(network) if network else 0,
        "environment": ENV
    }

@app.post("/orders")
async def handle_order(order: Order):
    try:
        result = await process_order(router, order)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Order processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/network/status")
async def get_network_status():
    if not network:
        raise HTTPException(status_code=503, detail="Network not initialized")
    
    return {
        "nodes": [
            {
                "id": node.shop.id,
                "location": {
                    "lat": node.shop.location.latitude,
                    "lon": node.shop.location.longitude
                },
                "capacity": node.shop.daily_capacity,
                "active_orders": len(node.assigned_orders)
            }
            for node in network
        ],
        "environment": ENV
    }

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env",
        choices=["development", "production"],
        default="development",
        help="Specify environment (development or production)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Specify port number"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    os.environ["ENVIRONMENT"] = args.env
    ENV = args.env
    IS_PROD = ENV == "production"
    
    if ENV == "development":
        # For development, use command line uvicorn
        logger.info("Please run using: uvicorn api:app --reload --port 8000")
        import sys
        sys.exit(1)
    else:
        # For production, run directly
        import uvicorn
        uvicorn.run(
            "api:app",
            host="0.0.0.0",
            port=args.port,
            log_level="info"
        )