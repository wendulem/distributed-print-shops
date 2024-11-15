from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import argparse
from typing import Optional

from src.models.order import Order
from src.routing.router import OrderRouter
from src.network.discovery import NetworkDiscovery
from src.models.shop import PrintShop

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "development")
IS_PROD = ENV == "production"

# Shared state
network: Optional[dict[str, PrintShop]] = None
router: Optional[OrderRouter] = None

app = FastAPI()

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "node_count": len(network) if network else 0,
        "environment": ENV
    }

@app.post("/orders")
async def handle_order(order: Order):
    if not network or not router:
        raise HTTPException(status_code=503, detail="Network not initialized")

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
                "id": node.id,
                "location": {
                    "lat": node.location.latitude,
                    "lon": node.location.longitude
                },
                "capacity": node.daily_capacity,
                "active_orders": len(node.assigned_orders)
            }
            for node in network.values()
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