import pytest
import asyncio
from datetime import datetime, timedelta

from src.models.shop import PrintShop, Location, Capability, ShopStatus
from src.network.discovery import NetworkDiscovery
from src.network.node import PrintShopNode
from src.models.cluster import Cluster

@pytest.fixture
def sample_shops():
    """Create a set of sample shops for testing"""
    return [
        PrintShop(
            id="sf-1",
            name="SF Print Co",
            location=Location(37.7749, -122.4194),  # SF
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        ),
        PrintShop(
            id="sf-2",
            name="SF Custom Prints",
            location=Location(37.7858, -122.4064),  # Also SF
            capabilities={Capability.TSHIRT, Capability.MUG},
            daily_capacity=150
        ),
        PrintShop(
            id="oak-1",
            name="Oakland Prints",
            location=Location(37.8044, -122.2712),  # Oakland
            capabilities={Capability.TSHIRT, Capability.POSTER},
            daily_capacity=120
        ),
        PrintShop(
            id="la-1",
            name="LA Prints",
            location=Location(34.0522, -118.2437),  # LA
            capabilities={Capability.TSHIRT, Capability.BOTTLE},
            daily_capacity=200
        )
    ]

@pytest.fixture
def discovery():
    """Create a fresh NetworkDiscovery instance"""
    return NetworkDiscovery()

@pytest.mark.asyncio
async def test_node_discovery(discovery, sample_shops):
    """Test basic node discovery and registration"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        assert discovery.add_node(node), f"Failed to add node {shop.id}"
    
    # Verify nodes were added
    assert len(discovery.nodes) == len(sample_shops), "Not all nodes were added"
    
    # Initialize network
    await discovery.initialize()
    
    # Verify all nodes are present
    for shop in sample_shops:
        assert shop.id in discovery.nodes, f"Node {shop.id} not found"

@pytest.mark.asyncio
async def test_cluster_formation(discovery, sample_shops):
    """Test automatic cluster formation based on geography"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    await discovery.initialize()
    
    # Verify clusters were formed
    assert len(discovery.clusters) > 0, "No clusters were formed"
    
    # Verify SF and Oakland shops are in same cluster
    bay_area_shops = {"sf-1", "sf-2", "oak-1"}
    bay_area_cluster = None
    
    for cluster in discovery.clusters.values():
        shop_ids = {shop.id for shop in cluster.shops}
        if bay_area_shops & shop_ids:  # If intersection exists
            bay_area_cluster = cluster
            break
    
    assert bay_area_cluster is not None, "Bay Area cluster not found"
    assert all(shop.id in [s.id for s in bay_area_cluster.shops] 
              for shop in sample_shops if shop.id in bay_area_shops), \
        "Bay Area shops should be in same cluster"
    
    # Verify LA shop is in different cluster
    la_shop = next(shop for shop in sample_shops if shop.id == "la-1")
    assert any(la_shop in cluster.shops 
              for cluster in discovery.clusters.values() 
              if cluster != bay_area_cluster), \
        "LA shop should be in different cluster"

@pytest.mark.asyncio
async def test_node_health_monitoring(discovery, sample_shops):
    """Test health monitoring of nodes"""
    # Add nodes
    nodes = []
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
        nodes.append(node)
    
    await discovery.initialize()
    
    # Simulate node failure
    failed_node = nodes[0]
    failed_node.shop.status = ShopStatus.OFFLINE
    failed_node.shop.last_heartbeat = datetime.now() - timedelta(minutes=10)
    
    # Run health check
    await discovery._periodic_health_check()
    
    # Verify node is marked as unhealthy
    assert failed_node.shop.id in discovery.nodes, "Node should still exist"
    assert discovery.nodes[failed_node.shop.id].shop.status == ShopStatus.OFFLINE, \
        "Node should be marked as offline"

@pytest.mark.asyncio
async def test_dynamic_cluster_adjustment(discovery, sample_shops):
    """Test cluster adjustment when nodes join/leave"""
    # Add initial nodes
    initial_shops = sample_shops[:2]
    for shop in initial_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    await discovery.initialize()
    initial_cluster_count = len(discovery.clusters)
    
    # Add new node
    new_node = PrintShopNode(sample_shops[2])  # Add Oakland shop
    discovery.add_node(new_node)
    
    # Verify cluster adaptation
    assert len(discovery.clusters) >= initial_cluster_count, \
        "Cluster count should not decrease"
    
    # Verify new node was assigned to appropriate cluster
    assigned_cluster = None
    for cluster in discovery.clusters.values():
        if new_node.shop in cluster.shops:
            assigned_cluster = cluster
            break
    
    assert assigned_cluster is not None, "New node should be assigned to a cluster"
    assert any(shop.id.startswith("sf") 
              for shop in assigned_cluster.shops), \
        "Oakland node should cluster with SF nodes"

@pytest.mark.asyncio
async def test_nearest_nodes_search(discovery, sample_shops):
    """Test finding nearest nodes to a location"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    await discovery.initialize()
    
    # Test location (SF downtown)
    test_location = Location(37.7749, -122.4194)
    
    # Get nearest nodes
    nearest_nodes = discovery.get_nearest_nodes(test_location, limit=2)
    
    # Verify nearest nodes are SF shops
    assert len(nearest_nodes) == 2, "Should return 2 nearest nodes"
    assert all(node.id.startswith("sf") for node in nearest_nodes), \
        "Nearest nodes should be SF shops"

@pytest.mark.asyncio
async def test_network_metrics(discovery, sample_shops):
    """Test network metrics calculation"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    await discovery.initialize()
    
    # Get network status
    status = discovery.get_network_status()
    
    # Verify metrics
    assert status["metrics"]["total_nodes"] == len(sample_shops)
    assert status["metrics"]["active_nodes"] == len(sample_shops)
    assert status["metrics"]["total_clusters"] == len(discovery.clusters)
    
    # Verify capacity calculations
    expected_capacity = sum(shop.daily_capacity for shop in sample_shops)
    assert status["metrics"]["total_capacity"] == expected_capacity

@pytest.mark.asyncio
async def test_cluster_optimization(discovery, sample_shops):
    """Test periodic cluster optimization"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    await discovery.initialize()
    
    # Record initial cluster state
    initial_clusters = {
        cluster_id: set(cluster.shops) 
        for cluster_id, cluster in discovery.clusters.items()
    }
    
    # Run optimization
    discovery._optimize_clusters()
    
    # Verify cluster stability
    for cluster_id, initial_shops in initial_clusters.items():
        if cluster_id in discovery.clusters:
            current_shops = set(discovery.clusters[cluster_id].shops)
            # Shops should generally stay in their optimal clusters
            assert len(initial_shops & current_shops) > 0, \
                "Optimization should not completely reorganize stable clusters"

def test_remove_node(discovery, sample_shops):
    """Test node removal"""
    # Add nodes
    for shop in sample_shops:
        node = PrintShopNode(shop)
        discovery.add_node(node)
    
    # Remove a node
    node_to_remove = sample_shops[0].id
    discovery.remove_node(node_to_remove)
    
    # Verify node removal
    assert node_to_remove not in discovery.nodes, "Node should be removed"
    
    # Verify node is removed from clusters
    for cluster in discovery.clusters.values():
        assert not any(shop.id == node_to_remove for shop in cluster.shops), \
            "Node should be removed from clusters"