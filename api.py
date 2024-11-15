# api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

# Import from src
from src.main import initialize_network, process_order
from src.models.order import Order
from src.routing.router import OrderRouter

app = FastAPI()

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize your network when the API starts
network = None
router = None

@app.on_event("startup")
async def startup_event():
    global network, router
    nodes = await initialize_network()  # Your existing initialization
    network = nodes
    router = OrderRouter(nodes)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "node_count": len(network) if network else 0}

@app.post("/orders")
async def handle_order(order: Order):
    try:
        result = await process_order(router, order)  # Your existing order processing
        return {"status": "success", "result": result}
    except Exception as e:
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
        ]
    }

# The main.py stays exactly as we had it before
# But now you can run the system in two ways:

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))