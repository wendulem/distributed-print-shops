class MessageTypes:
    # Node lifecycle and health
    NODE_HELLO = "node.hello"           # Was HELLO in protocol
    NODE_HEARTBEAT = "node.heartbeat"   # Was HEARTBEAT
    NODE_BYE = "node.bye"               # Was BYE
    NODE_STATUS = "node.status"
    NODE_CAPACITY = "node.capacity"     # Combines CAPACITY_UPDATE and CAPACITY_QUERY
    
    # Order handling
    ORDER_NEW = "order.new"             # Was ORDER_REQUEST
    ORDER_RESPONSE = "order.response"    # Keep from protocol
    ORDER_FORWARD = "order.forward"      # Keep from protocol
    ORDER_ALLOCATED = "order.allocated"  # New state
    ORDER_STARTED = "order.started"      # New state
    ORDER_COMPLETED = "order.completed"  # New state
    ORDER_FAILED = "order.failed"        # New state
    
    # Inventory management
    INVENTORY_QUERY = "inventory.query"      # Keep from protocol
    INVENTORY_UPDATE = "inventory.update"    # Keep from protocol
    INVENTORY_TRANSFER = "inventory.transfer" # Keep from protocol
    
    # Cluster management
    CLUSTER_JOIN = "cluster.join"       # Was CLUSTER_JOIN
    CLUSTER_LEAVE = "cluster.leave"     # Was CLUSTER_LEAVE
    CLUSTER_UPDATE = "cluster.update"   # Was CLUSTER_UPDATE
    CLUSTER_STATUS = "cluster.status"   # New addition
    CLUSTER_CAPACITY = "cluster.capacity" # New addition
    
    # System-wide messages
    SYSTEM_STATUS = "system.status"
    SYSTEM_ALERT = "system.alert"

    @classmethod
    def to_enum(cls, value: str) -> str:
        """Convert dot notation to enum format"""
        return value.upper().replace(".", "_")
    
    @classmethod
    def from_enum(cls, enum: str) -> str:
        """Convert enum format to dot notation"""
        return enum.lower().replace("_", ".")