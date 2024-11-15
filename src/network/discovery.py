from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import asyncio
import logging
import math
from datetime import datetime, timedelta

from ..models.shop import PrintShop, Location, ShopStatus
from ..models.cluster import Cluster, ClusterMetrics

logger = logging.getLogger(__name__)

@dataclass
class NetworkMetrics:
    total_nodes: int = 0
    active_nodes: int = 0
    total_clusters: int = 0
    total_capacity: int = 0
    available_capacity: int = 0
    last_updated: datetime = datetime.now()

class NetworkDiscovery:
    def __init__(self, initial_nodes: Optional[List[PrintShop]] = None):
        self.nodes: Dict[str, PrintShop] = {}
        self.clusters: Dict[str, Cluster] = {}
        self.metrics = NetworkMetrics()
        
        # Configuration
        self.cluster_radius_miles = 100.0  # Maximum radius for a cluster
        self.health_check_interval = 60  # Seconds between health checks
        self.node_timeout = 300  # Seconds before considering a node offline
        
        # Initialize with any provided nodes
        if initial_nodes:
            for node in initial_nodes:
                self.add_node(node)

    async def initialize(self):
        """Start background tasks"""
        asyncio.create_task(self._periodic_health_check())
        asyncio.create_task(self._periodic_cluster_optimization())

    def add_node(self, node: PrintShop) -> bool:
        """Add a new node to the network"""
        try:
            # Add to nodes dictionary
            self.nodes[node.id] = node
            
            # Try to add to existing cluster
            assigned_cluster = self._assign_to_cluster(node)
            
            if not assigned_cluster:
                # Create new cluster if needed
                cluster_id = f"cluster-{len(self.clusters) + 1}"
                new_cluster = Cluster(
                    id=cluster_id,
                    center_location=node.location,
                    shops={node}
                )
                self.clusters[cluster_id] = new_cluster
                logger.info(f"Created new cluster {cluster_id} for node {node.id}")
            
            self._update_metrics()
            return True
            
        except Exception as e:
            logger.error(f"Failed to add node {node.id}: {e}")
            return False

    def remove_node(self, node_id: str):
        """Remove a node from the network"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            
            # Remove from clusters
            for cluster in self.clusters.values():
                if node in cluster.shops:
                    cluster.remove_shop(node)
            
            # Remove from nodes
            del self.nodes[node_id]
            self._update_metrics()
            
            # Clean up empty clusters
            empty_clusters = [
                cid for cid, cluster in self.clusters.items()
                if not cluster.shops
            ]
            for cid in empty_clusters:
                del self.clusters[cid]

    def _assign_to_cluster(self, node: PrintShop) -> Optional[Cluster]:
        """Attempt to assign a node to an existing cluster"""
        best_cluster = None
        min_distance = float('inf')
        
        for cluster in self.clusters.values():
            distance = cluster.center_location.distance_to(node.location)
            if distance <= self.cluster_radius_miles and distance < min_distance:
                best_cluster = cluster
                min_distance = distance
        
        if best_cluster:
            best_cluster.add_shop(node)
            logger.info(f"Added node {node.id} to cluster {best_cluster.id}")
            return best_cluster
            
        return None

    def get_nearest_nodes(self, location: Location, limit: int = 5) -> List[PrintShop]:
        """Get the nearest nodes to a location"""
        nodes_with_distance = [
            (node, node.location.distance_to(location))
            for node in self.nodes.values()
            if node.status == ShopStatus.ONLINE
        ]
        
        nodes_with_distance.sort(key=lambda x: x[1])
        return [node for node, _ in nodes_with_distance[:limit]]

    def find_cluster_for_location(self, location: Location) -> Optional[Cluster]:
        """Find the most appropriate cluster for a given location"""
        best_cluster = None
        min_distance = float('inf')
        
        for cluster in self.clusters.values():
            distance = cluster.center_location.distance_to(location)
            if distance < min_distance:
                best_cluster = cluster
                min_distance = distance
                
        return best_cluster

    async def _periodic_health_check(self):
        """Periodically check health of all nodes"""
        while True:
            try:
                current_time = datetime.now()
                
                for node in list(self.nodes.values()):
                    # Check last heartbeat
                    if (current_time - node.last_heartbeat).total_seconds() > self.node_timeout:
                        if node.status != ShopStatus.OFFLINE:
                            logger.warning(f"Node {node.id} appears to be offline")
                            node.update_status(ShopStatus.OFFLINE, "Heartbeat timeout")
                
                self._update_metrics()
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                
            await asyncio.sleep(self.health_check_interval)

    async def _periodic_cluster_optimization(self):
        """Periodically optimize cluster assignments"""
        while True:
            try:
                self._optimize_clusters()
            except Exception as e:
                logger.error(f"Error in cluster optimization: {e}")
                
            await asyncio.sleep(300)  # Run every 5 minutes

    def _optimize_clusters(self):
        """Optimize cluster assignments based on current network state"""
        # This is a simple implementation - could be made more sophisticated
        changed = False
        
        for node in self.nodes.values():
            current_cluster = None
            for cluster in self.clusters.values():
                if node in cluster.shops:
                    current_cluster = cluster
                    break
            
            # Try to find a better cluster
            better_cluster = self._assign_to_cluster(node)
            if better_cluster and better_cluster != current_cluster:
                if current_cluster:
                    current_cluster.remove_shop(node)
                changed = True
        
        if changed:
            self._update_metrics()

    def _update_metrics(self):
        """Update network metrics"""
        self.metrics.total_nodes = len(self.nodes)
        self.metrics.active_nodes = sum(
            1 for node in self.nodes.values()
            if node.status == ShopStatus.ONLINE
        )
        self.metrics.total_clusters = len(self.clusters)
        self.metrics.total_capacity = sum(
            node.daily_capacity for node in self.nodes.values()
        )
        self.metrics.available_capacity = sum(
            node.current_capacity for node in self.nodes.values()
            if node.status == ShopStatus.ONLINE
        )
        self.metrics.last_updated = datetime.now()

    def get_network_status(self) -> Dict:
        """Get current network status"""
        return {
            "metrics": {
                "total_nodes": self.metrics.total_nodes,
                "active_nodes": self.metrics.active_nodes,
                "total_clusters": self.metrics.total_clusters,
                "total_capacity": self.metrics.total_capacity,
                "available_capacity": self.metrics.available_capacity,
                "last_updated": self.metrics.last_updated.isoformat()
            },
            "clusters": {
                cluster.id: cluster.get_status()
                for cluster in self.clusters.values()
            }
        }