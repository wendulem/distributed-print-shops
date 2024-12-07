from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime

from ..models.shop import Location
from ..models.cluster import Cluster

logger = logging.getLogger(__name__)

@dataclass
class NetworkMetrics:
    total_clusters: int = 0
    total_capacity: int = 0
    available_capacity: int = 0
    last_updated: datetime = datetime.now()

class NetworkDiscovery:
    """
    The NetworkDiscovery class now focuses solely on managing clusters.
    It is responsible for:
    - Tracking all known clusters in the network.
    - Handling cluster formation requests.
    - Finding clusters by location and returning nearby clusters.
    - Running periodic health checks and optimization tasks at the cluster level.
    """

    def __init__(self, initial_clusters: Optional[List[Cluster]] = None):
        # Clusters identified by a unique cluster ID
        self.clusters: Dict[str, Cluster] = {}
        self.metrics = NetworkMetrics()

        # Configuration
        self.health_check_interval = 60   # Seconds between cluster health checks
        self.optimization_interval = 300  # Seconds between cluster optimizations

        # Initialize with any provided clusters
        if initial_clusters:
            for cluster in initial_clusters:
                self.add_cluster(cluster)

    async def initialize(self):
        """
        Start background tasks for cluster-level operations.
        This might include listening for cluster formation requests
        (not shown here, as it depends on external integration) and
        starting periodic tasks.
        """
        asyncio.create_task(self._periodic_health_check())
        asyncio.create_task(self._periodic_cluster_optimization())
        logger.info("NetworkDiscovery initialized for cluster-based management")

    def add_cluster(self, cluster: Cluster):
        """
        Add a new cluster to the network. This would typically be called
        when a cluster formation request is granted or when a new cluster
        is discovered.
        """
        self.clusters[cluster.id] = cluster
        self._update_metrics()
        logger.info(f"Added cluster {cluster.id} to the network")

    def remove_cluster(self, cluster_id: str):
        """
        Remove an existing cluster from the network. This might happen if
        a cluster dissolves, merges with another, or is decommissioned.
        """
        if cluster_id in self.clusters:
            del self.clusters[cluster_id]
            self._update_metrics()
            logger.info(f"Removed cluster {cluster_id} from the network")

    def handle_cluster_formation_request(self, location: Location) -> Cluster:
        """
        Handle a request to form or find a suitable cluster for a given location.
        1. Attempt to find an existing cluster that is near this location.
        2. If no suitable cluster is found, create a new cluster at that location.
        """
        cluster = self.find_cluster_by_location(location)
        if cluster:
            logger.info(f"Found existing cluster {cluster.id} for location ({location.latitude}, {location.longitude})")
            return cluster
        else:
            # Create a new cluster centered at this location
            new_cluster_id = f"cluster-{len(self.clusters) + 1}"
            new_cluster = Cluster(id=new_cluster_id, center_location=location, radius_miles=self.cluster_radius_miles)
            self.add_cluster(new_cluster)
            logger.info(f"Created new cluster {new_cluster.id} for location ({location.latitude}, {location.longitude})")
            return new_cluster

    def find_cluster_by_location(self, location: Location) -> Optional[Cluster]:
        """
        Find the most appropriate cluster for a given location.
        Typically, this means the closest cluster center to the given location.
        """
        best_cluster = None
        min_distance = float('inf')

        for cluster in self.clusters.values():
            distance = cluster.center_location.distance_to(location)
            if distance < min_distance:
                best_cluster = cluster
                min_distance = distance

        return best_cluster

    def get_nearby_clusters(self, location: Location, limit: int = 5) -> List[Cluster]:
        """
        Return a list of clusters sorted by their distance to the provided location,
        up to a specified limit.
        """
        clusters_with_distance = [
            (cluster, cluster.center_location.distance_to(location))
            for cluster in self.clusters.values()
        ]

        clusters_with_distance.sort(key=lambda x: x[1])
        return [cluster for cluster, _ in clusters_with_distance[:limit]]

    async def _periodic_health_check(self):
        """
        Periodically check the health of all clusters by sending heartbeat messages.
        Clusters (and their nodes) should respond to heartbeats.
        If a cluster fails to respond or shows no activity, we might take action.
        """
        while True:
            try:
                for cluster_id, cluster in self.clusters.items():
                    # Send a heartbeat request to the cluster
                    msg = self.protocol.create_message(MessageType.HEARTBEAT, {"cluster_id": cluster_id})
                    # In a full system, this would send the message to the cluster's coordination endpoint
                    # and we'd handle a response. Here we assume handle_cluster_message on cluster side.
                    cluster.handle_cluster_message(msg)
                    
                    # After sending heartbeat, we might wait for a response or check cluster state.
                    # For simplicity, assume cluster updates internal metrics or responds synchronously.
                    # In a real system, cluster's nodes respond asynchronously, and we'd track responses.
                
                self._update_metrics()
            except Exception as e:
                logger.error(f"Error in cluster health check: {e}")

            await asyncio.sleep(self.health_check_interval)

    async def _periodic_cluster_optimization(self):
        """
        Periodically optimize cluster assignments or distribution.
        Could:
        - Merge underutilized clusters
        - Split large clusters
        - Rebalance load by adjusting cluster radius or reassigning nodes
        """
        while True:
            try:
                self._optimize_clusters()
            except Exception as e:
                logger.error(f"Error in cluster optimization: {e}")

            await asyncio.sleep(self.optimization_interval)

    def _optimize_clusters(self):
        """
        I could use this to:
        - Check if some clusters are underutilized and merge them.
        - Split large clusters into smaller ones for better load distribution.
        For now, it doesn't change anything. In a full system, this would integrate
        with routing or discovery logic to adjust cluster boundaries.
        """
        # Placeholder: no-op optimization
        pass

    def _update_metrics(self):
        """
        Update network-level metrics based on the current state of all clusters.
        The metrics here aggregate cluster capacities.
        """
        self.metrics.total_clusters = len(self.clusters)
        total_capacity = 0
        available_capacity = 0

        # Assuming each cluster can report its current capacity and availability
        for cluster in self.clusters.values():
            cluster_status = cluster.get_cluster_status()
            metrics = cluster_status.get("metrics", {})
            total_capacity += metrics.get("total_capacity", 0)
            available_capacity += metrics.get("available_capacity", 0)

        self.metrics.total_capacity = total_capacity
        self.metrics.available_capacity = available_capacity
        self.metrics.last_updated = datetime.now()

    def get_network_status(self) -> Dict:
        """
        Get current network status, focusing on cluster-level metrics and states.
        """
        return {
            "metrics": {
                "total_clusters": self.metrics.total_clusters,
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "last_updated": self.metrics.last_updated.isoformat()
            },
            "clusters": {
                cluster.id: cluster.get_cluster_status()
                for cluster in self.clusters.values()
            }
        }

    # Additional methods could be added here:
    # - methods to integrate with protocol or discovery logic, etc.
