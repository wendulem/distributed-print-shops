from typing import Dict, Optional
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime

from ..models.shop import Location
from ..infrastructure.messaging import MessageTransport
from ..infrastructure.messaging.types import MessageTypes

logger = logging.getLogger(__name__)

@dataclass
class NetworkMetrics:
    total_clusters: int = 0
    total_capacity: int = 0
    available_capacity: int = 0
    last_updated: datetime = datetime.now()

class NetworkDiscovery:
    """
    NetworkDiscovery coordinates cluster discovery and management through messaging.
    It observes cluster formation/dissolution and maintains network metrics
    without directly managing cluster objects.
    """
    def __init__(self, message_transport: MessageTransport):
        self.transport = message_transport
        self.metrics = NetworkMetrics()
        
        # Track cluster metadata
        self.cluster_locations: Dict[str, Location] = {}
        self.cluster_metrics: Dict[str, dict] = {}
        
        # Configuration
        self.health_check_interval = 60
        self.optimization_interval = 300

    async def start(self):
        """Initialize discovery service and subscribe to network events"""
        # Subscribe to cluster lifecycle events
        await self.transport.subscribe("cluster.announce", self._handle_cluster_announce)
        await self.transport.subscribe("cluster.shutdown", self._handle_cluster_shutdown)
        await self.transport.subscribe("cluster.status", self._handle_cluster_status)
        
        # Subscribe to node discovery events
        await self.transport.subscribe("node.hello", self._handle_node_hello)
        await self.transport.subscribe("node.bye", self._handle_node_bye)
        
        # Start background tasks
        asyncio.create_task(self._periodic_health_check())
        asyncio.create_task(self._periodic_optimization())
        
        logger.info("NetworkDiscovery started")

    async def handle_node_discovery(self, location: Location) -> str:
        """Find or create suitable cluster for node location"""
        cluster_id = await self._find_best_cluster(location)
        
        if not cluster_id:
            # Request new cluster formation
            cluster_id = f"cluster-{len(self.cluster_locations) + 1}"
            
            await self.transport.publish("cluster.create", {
                "cluster_id": cluster_id,
                "location": location.to_dict(),
                "radius_miles": 100.0  # Default radius
            })
            
            # Wait briefly for cluster announcement
            await asyncio.sleep(1)
        
        return cluster_id

    async def _find_best_cluster(self, location: Location) -> Optional[str]:
        """Find most appropriate existing cluster for location"""
        best_cluster_id = None
        min_distance = float('inf')

        for cluster_id, cluster_location in self.cluster_locations.items():
            distance = cluster_location.distance_to(location)
            if distance < min_distance:
                min_distance = distance
                best_cluster_id = cluster_id

        return best_cluster_id

    async def _handle_cluster_announce(self, message: dict):
        """Handle new cluster announcement"""
        data = message.get("data", {})
        cluster_id = data.get("cluster_id")
        location_data = data.get("location", {})
        
        if cluster_id and location_data:
            self.cluster_locations[cluster_id] = Location(**location_data)
            logger.info(f"Registered new cluster {cluster_id}")
            await self._update_metrics()

    async def _handle_cluster_shutdown(self, message: dict):
        """Handle cluster shutdown"""
        cluster_id = message.get("data", {}).get("cluster_id")
        if cluster_id in self.cluster_locations:
            self.cluster_locations.pop(cluster_id)
            self.cluster_metrics.pop(cluster_id, None)
            logger.info(f"Removed cluster {cluster_id}")
            await self._update_metrics()

    async def _handle_cluster_status(self, message: dict):
        """Handle cluster status update"""
        data = message.get("data", {})
        cluster_id = data.get("cluster_id")
        metrics = data.get("metrics", {})
        
        if cluster_id and metrics:
            self.cluster_metrics[cluster_id] = metrics
            await self._update_metrics()

    async def _handle_node_hello(self, message: dict):
        """Handle new node announcement"""
        data = message.get("data", {})
        location_data = data.get("location", {})
        
        if location_data:
            location = Location(**location_data)
            cluster_id = await self.handle_node_discovery(location)
            
            if cluster_id:
                # Inform node of its cluster assignment
                await self.transport.publish(f"node.{data['node_id']}.cluster", {
                    "cluster_id": cluster_id
                })

    async def _handle_node_bye(self, message: dict):
        """Handle node departure"""
        # We don't need to do much here as clusters handle their own membership
        logger.info(f"Node {message.get('data', {}).get('node_id')} departing network")

    async def _periodic_health_check(self):
        """Periodic cluster health monitoring"""
        while True:
            try:
                # Request status updates from all clusters
                await self.transport.publish("cluster.health.check", {
                    "timestamp": datetime.now().isoformat()
                })
                
                # Wait for responses via _handle_cluster_status
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in health check: {e}")

    async def _periodic_optimization(self):
        """Periodic cluster optimization"""
        while True:
            try:
                await self._optimize_clusters()
            except Exception as e:
                logger.error(f"Error in optimization: {e}")
            await asyncio.sleep(self.optimization_interval)

    async def _optimize_clusters(self):
        """Optimize cluster distribution"""
        # Example optimization: merge underutilized clusters
        underutilized = []
        for cluster_id, metrics in self.cluster_metrics.items():
            if metrics.get("utilization", 1.0) < 0.3:  # Less than 30% utilized
                underutilized.append(cluster_id)

        if len(underutilized) > 1:
            await self.transport.publish("cluster.optimize", {
                "action": "merge",
                "clusters": underutilized
            })

    async def _update_metrics(self):
        """Update network metrics from cluster data"""
        self.metrics.total_clusters = len(self.cluster_locations)
        self.metrics.total_capacity = sum(
            m.get("total_capacity", 0) for m in self.cluster_metrics.values()
        )
        self.metrics.available_capacity = sum(
            m.get("available_capacity", 0) for m in self.cluster_metrics.values()
        )
        self.metrics.last_updated = datetime.now()

    def get_network_status(self) -> dict:
        """Get current network status"""
        return {
            "metrics": {
                "total_clusters": self.metrics.total_clusters,
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "last_updated": self.metrics.last_updated.isoformat()
            },
            "clusters": {
                cluster_id: {
                    "location": self.cluster_locations[cluster_id].to_dict(),
                    "metrics": self.cluster_metrics.get(cluster_id, {})
                }
                for cluster_id in self.cluster_locations
            }
        }