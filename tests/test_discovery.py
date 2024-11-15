import pytest
import asyncio
import requests
from datetime import datetime, timedelta

from src.models.shop import PrintShop, Location, Capability, ShopStatus
from src.models.order import Order, OrderItem, OrderPriority
from src.models.cluster import Cluster

@pytest.fixture
def sample_shops():
    return [
        PrintShop(
            id="sf-1", name="SF Print Co", location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE}, daily_capacity=100
        ),
        PrintShop(
            id="sf-2", name="SF Custom Prints", location=Location(37.7858, -122.4064),
            capabilities={Capability.TSHIRT, Capability.MUG}, daily_capacity=150
        ),
        PrintShop(
            id="oak-1", name="Oakland Prints", location=Location(37.8044, -122.2712),
            capabilities={Capability.TSHIRT, Capability.POSTER}, daily_capacity=120
        ),
        PrintShop(
            id="la-1", name="LA Prints", location=Location(34.0522, -118.2437),
            capabilities={Capability.TSHIRT, Capability.BOTTLE}, daily_capacity=200
        )
    ]

@pytest.mark.asyncio
async def test_node_discovery_and_registration(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    assert len(network_status["nodes"]) == len(sample_shops)

@pytest.mark.asyncio
async def test_cluster_formation(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    assert len(network_status["clusters"]) > 0

    bay_area_shops = [node for node in network_status["nodes"] if node["id"].startswith("sf") or node["id"].startswith("oak")]
    assert all(node["id"] in [shop["id"] for shop in bay_area_shops] for shop in sample_shops if shop.id.startswith("sf") or shop.id.startswith("oak"))

    la_shop = next((node for node in network_status["nodes"] if node["id"] == "la-1"), None)
    assert la_shop is not None
    assert la_shop not in bay_area_shops

@pytest.mark.asyncio
async def test_order_processing(sample_shops):
    order = {
        "id": "test-order-1",
        "customer_location": {
            "latitude": 37.7749,
            "longitude": -122.4194
        },
        "items": [
            {
                "product_type": "TSHIRT",
                "quantity": 50,
                "design_url": "https://example.com/design1"
            },
            {
                "product_type": "HOODIE",
                "quantity": 30,
                "design_url": "https://example.com/design2"
            }
        ],
        "priority": "NORMAL"
    }

    response = requests.post("http://localhost:8000/orders", json=order)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    order = {
        "id": "test-order-2",
        "customer_location": {
            "latitude": 34.0522,
            "longitude": -118.2437
        },
        "items": [
            {
                "product_type": "TSHIRT",
                "quantity": 20,
                "design_url": "https://example.com/design3"
            },
            {
                "product_type": "BOTTLE",
                "quantity": 10,
                "design_url": "https://example.com/design4"
            }
        ],
        "priority": "RUSH"
    }

    response = requests.post("http://localhost:8000/orders", json=order)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@pytest.mark.asyncio
async def test_network_status_and_metrics(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    assert "nodes" in network_status
    assert network_status["metrics"]["total_nodes"] == len(sample_shops)
    assert network_status["metrics"]["active_nodes"] == len(sample_shops)
    assert network_status["metrics"]["total_clusters"] > 0
    assert network_status["metrics"]["total_capacity"] == sum(shop.daily_capacity for shop in sample_shops)

@pytest.mark.asyncio
async def test_node_failure_and_health_monitoring(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    failed_node = sample_shops[0]
    failed_node.status = ShopStatus.OFFLINE
    failed_node.last_heartbeat = datetime.now() - timedelta(minutes=10)

    response = requests.post(f"http://localhost:8000/shops/{failed_node.id}/heartbeat", json={
        "status": failed_node.status.value,
        "last_heartbeat": failed_node.last_heartbeat.isoformat()
    })
    assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    failed_node_info = next((node for node in network_status["nodes"] if node["id"] == failed_node.id), None)
    assert failed_node_info is not None
    assert failed_node_info["status"] == ShopStatus.OFFLINE.value

@pytest.mark.asyncio
async def test_nearest_nodes_search(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    sf_nodes = [node for node in network_status["nodes"] if node["id"].startswith("sf")]
    assert len(sf_nodes) == 2
    assert all(node["id"].startswith("sf") for node in sf_nodes)

@pytest.mark.asyncio
async def test_cluster_adaptation_and_order_routing(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    new_shop = PrintShop(
        id="sea-1", name="Seattle Prints", location=Location(47.6062, -122.3321),
        capabilities={Capability.TSHIRT, Capability.POSTER}, daily_capacity=100
    )
    response = requests.post("http://localhost:8000/neighbors", json={
        "node_id": new_shop.id,
        "url": f"http://localhost:8000/shops/{new_shop.id}"
    })
    assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    assert len(network_status["nodes"]) == len(sample_shops) + 1

    order = {
        "id": "test-order-3",
        "customer_location": {
            "latitude": 47.6062,
            "longitude": -122.3321
        },
        "items": [
            {
                "product_type": "TSHIRT",
                "quantity": 30,
                "design_url": "https://example.com/design5"
            },
            {
                "product_type": "POSTER",
                "quantity": 5,
                "design_url": "https://example.com/design6"
            }
        ],
        "priority": "NORMAL"
    }

    response = requests.post("http://localhost:8000/orders", json=order)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    seattle_node = next((node for node in network_status["nodes"] if node["id"] == "sea-1"), None)
    assert seattle_node is not None
    assert seattle_node["active_orders"] > 0

@pytest.mark.asyncio
async def test_cluster_optimization(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    initial_network_status = response.json()

    # Simulate node changes
    new_shop = PrintShop(
        id="sea-1", name="Seattle Prints", location=Location(47.6062, -122.3321),
        capabilities={Capability.TSHIRT, Capability.POSTER}, daily_capacity=100
    )
    response = requests.post("http://localhost:8000/neighbors", json={
        "node_id": new_shop.id,
        "url": f"http://localhost:8000/shops/{new_shop.id}"
    })
    assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    updated_network_status = response.json()

    # Verify cluster stability
    for cluster_id, initial_cluster in initial_network_status["clusters"].items():
        if cluster_id in updated_network_status["clusters"]:
            updated_cluster = updated_network_status["clusters"][cluster_id]
            assert len(set(shop["id"] for shop in initial_cluster["shops"]) & set(shop["id"] for shop in updated_cluster["shops"])) > 0, "Clusters should remain stable"

@pytest.mark.asyncio
async def test_node_removal(sample_shops):
    for shop in sample_shops:
        response = requests.post("http://localhost:8000/neighbors", json={
            "node_id": shop.id,
            "url": f"http://localhost:8000/shops/{shop.id}"
        })
        assert response.status_code == 200

    node_to_remove = sample_shops[0].id
    response = requests.delete(f"http://localhost:8000/shops/{node_to_remove}")
    assert response.status_code == 200

    response = requests.get("http://localhost:8000/network/status")
    assert response.status_code == 200
    network_status = response.json()
    assert not any(node["id"] == node_to_remove for node in network_status["nodes"])

    for cluster in network_status["clusters"].values():
        assert node_to_remove not in [node["id"] for node in cluster["shops"]]