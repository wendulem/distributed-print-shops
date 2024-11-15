import pytest
from datetime import datetime

from src.models.shop import PrintShop, Location, Capability, ShopStatus
from src.models.order import Order, OrderItem, OrderPriority
from src.models.cluster import Cluster
from src.routing.router import OrderRouter, RoutingResult
from src.routing.optimizer import RouteOptimizer, ShopScore

@pytest.fixture
def shops():
    """Create a set of test shops"""
    return [
        PrintShop(
            id="sf-1",
            name="SF Print Co",
            location=Location(37.7749, -122.4194),
            capabilities={Capability.TSHIRT, Capability.HOODIE},
            daily_capacity=100
        ),
        PrintShop(
            id="sf-2",
            name="SF Custom Prints",
            location=Location(37.7858, -122.4064),
            capabilities={Capability.TSHIRT, Capability.MUG},
            daily_capacity=150
        ),
        PrintShop(
            id="la-1",
            name="LA Prints",
            location=Location(34.0522, -118.2437),
            capabilities={Capability.TSHIRT, Capability.BOTTLE},
            daily_capacity=200
        )
    ]

@pytest.fixture
def clusters(shops):
    """Create test clusters"""
    sf_cluster = Cluster(
        id="sf-cluster",
        center_location=shops[0].location,
        radius_miles=50.0
    )
    sf_cluster.add_shop(shops[0])
    sf_cluster.add_shop(shops[1])
    
    la_cluster = Cluster(
        id="la-cluster",
        center_location=shops[2].location,
        radius_miles=50.0
    )
    la_cluster.add_shop(shops[2])
    
    return [sf_cluster, la_cluster]

@pytest.fixture
def router(shops, clusters):
    """Create test router"""
    return OrderRouter(shops, clusters)

@pytest.fixture
def optimizer():
    """Create test optimizer"""
    return RouteOptimizer()

class TestOptimizer:
    def test_shop_scoring(self, optimizer, shops):
        """Test shop scoring logic"""
        order = Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),  # SF location
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        scores = optimizer.score_shops(order, shops)
        assert scores, "Should return shop scores"
        assert isinstance(scores[0], ShopScore)
        
        # SF shops should score higher than LA shop
        sf_scores = [s for s in scores if s.shop_id.startswith("sf")]
        la_scores = [s for s in scores if s.shop_id.startswith("la")]
        assert all(sf.score > la.score for sf in sf_scores for la in la_scores), \
            "SF shops should score higher for SF order"

    def test_distance_scoring(self, optimizer, shops):
        """Test distance-based scoring"""
        sf_location = Location(37.7749, -122.4194)
        la_location = Location(34.0522, -118.2437)
        
        sf_score = optimizer._calculate_distance_score(shops[0].location, sf_location)
        la_score = optimizer._calculate_distance_score(shops[0].location, la_location)
        
        assert sf_score > la_score, "Closer locations should score higher"

    def test_capacity_scoring(self, optimizer, shops):
        """Test capacity-based scoring"""
        order = Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        # Test with full capacity
        score1 = optimizer._calculate_capacity_score(shops[0], order)
        
        # Test with reduced capacity
        shops[0].reserve_capacity(50)
        score2 = optimizer._calculate_capacity_score(shops[0], order)
        
        assert score1 > score2, "Higher capacity should score better"

class TestRouter:
    @pytest.mark.asyncio
    async def test_basic_routing(self, router):
        """Test basic order routing"""
        order = Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        result = await router.route_order(order)
        assert result.success
        assert result.node_assignments
        assert all(isinstance(k, str) and isinstance(v, list) 
                  for k, v in result.node_assignments.items())

    @pytest.mark.asyncio
    async def test_geographic_routing(self, router):
        """Test geographic routing preferences"""
        # SF order
        sf_order = Order(
            id="sf-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        # LA order
        la_order = Order(
            id="la-order",
            customer_location=Location(34.0522, -118.2437),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design2"
                )
            ]
        )
        
        sf_result = await router.route_order(sf_order)
        la_result = await router.route_order(la_order)
        
        assert any(shop_id.startswith("sf") for shop_id in sf_result.node_assignments)
        assert any(shop_id.startswith("la") for shop_id in la_result.node_assignments)

    @pytest.mark.asyncio
    async def test_split_routing(self, router):
        """Test order splitting across shops"""
        large_order = Order(
            id="large-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=250,  # Larger than any single shop capacity
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        result = await router.route_order(large_order)
        assert result.success
        assert len(result.node_assignments) > 1, "Large order should be split"

    @pytest.mark.asyncio
    async def test_capacity_handling(self, router, shops):
        """Test handling of capacity constraints"""
        # Fill up first shop
        shops[0].reserve_capacity(shops[0].daily_capacity)
        
        order = Order(
            id="test-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        result = await router.route_order(order)
        assert result.success
        assert shops[0].id not in result.node_assignments, \
            "Should not assign to full shop"

    @pytest.mark.asyncio
    async def test_priority_routing(self, router):
        """Test priority-based routing"""
        rush_order = Order(
            id="rush-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type=Capability.TSHIRT.value,
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ],
            priority=OrderPriority.RUSH
        )
        
        result = await router.route_order(rush_order)
        assert result.success
        assert result.estimated_time < 24.0, "Rush orders should have faster estimate"

    @pytest.mark.asyncio
    async def test_routing_failures(self, router):
        """Test handling of impossible routing scenarios"""
        impossible_order = Order(
            id="impossible-order",
            customer_location=Location(37.7749, -122.4194),
            items=[
                OrderItem(
                    product_type="INVALID_PRODUCT",
                    quantity=50,
                    design_url="https://example.com/design1"
                )
            ]
        )
        
        result = await router.route_order(impossible_order)
        assert not result.success
        assert not result.node_assignments
        assert "error" in result.details

    def test_routing_stats(self, router):
        """Test routing statistics tracking"""
        stats = router.get_routing_stats()
        assert "total_orders" in stats
        assert "successful_routes" in stats
        assert "failed_routes" in stats
        assert "success_rate" in stats