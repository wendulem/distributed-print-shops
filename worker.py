# worker.py
import asyncio
import os
import redis
import json
import requests
from time import sleep

# Import from src
from src.network.discovery import get_neighbor_urls
from src.models.shop import PrintShop, Location
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url)
NODE_ID = os.getenv('NODE_ID')

async def discover_neighbors():
    """Periodically discover and update neighbors"""
    while True:
        try:
            # Get all nodes from Heroku platform API
            # You'll need to implement this based on how you're tracking nodes
            neighbor_urls = get_neighbor_urls()
            
            for url in neighbor_urls:
                try:
                    # Health check neighbor
                    response = requests.get(f"{url}/health")
                    if response.status_code == 200:
                        # Register with neighbor
                        requests.post(
                            f"{url}/neighbors",
                            json={
                                "node_id": NODE_ID,
                                "url": os.getenv('NODE_URL')
                            }
                        )
                except Exception:
                    continue
        except Exception as e:
            print(f"Error in neighbor discovery: {e}")
        
        await asyncio.sleep(60)  # Run every minute

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(discover_neighbors())