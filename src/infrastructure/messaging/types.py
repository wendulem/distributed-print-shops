from enum import Enum

class MessageTypes:
    # Node-related messages
    NODE_HEARTBEAT = "node.heartbeat"
    NODE_STATUS = "node.status"
    NODE_CAPACITY = "node.capacity"
    
    # Order-related messages
    ORDER_NEW = "order.new"
    ORDER_ALLOCATED = "order.allocated"
    ORDER_STARTED = "order.started"
    ORDER_COMPLETED = "order.completed"
    ORDER_FAILED = "order.failed"
    
    # Cluster-related messages
    CLUSTER_STATUS = "cluster.status"
    CLUSTER_CAPACITY = "cluster.capacity"
    
    # System-wide messages
    SYSTEM_STATUS = "system.status"
    SYSTEM_ALERT = "system.alert"
    
    # TODO cross-reference this with the rest of the codebase