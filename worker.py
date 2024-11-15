import asyncio
import os
import redis
import json
import requests
from time import sleep
from src.network.discovery import NetworkDiscovery
from src.models.shop import PrintShop, Location

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url)
NODE_ID = os.getenv('NODE_ID')
NODE_URL = os.getenv('NODE_URL')

async def discover_neighbors():
    """Periodically discover and update neighbors"""
    network_discovery = NetworkDiscovery()
    await network_discovery.initialize()

    while True:
        try:
            # Get all nearest active nodes
            nearest_nodes = network_discovery.get_nearest_nodes(
                Location(latitude=0, longitude=0), limit=5
            )

            for node in nearest_nodes:
                try:
                    # Register with neighbor
                    requests.post(
                        f"{node.url}/neighbors",
                        json={
                            "node_id": NODE_ID,
                            "url": NODE_URL
                        }
                    )
                except Exception:
                    continue
        except Exception as e:
            print(f"Error in neighbor discovery: {e}")

        await asyncio.sleep(60)  # Run every minute

if __name__ == "__main__":
    asyncio.run(discover_neighbors())