# Print Shop Network - Distributed Order Management System

## Overview
This system implements a distributed network of print shops that collaboratively handle print orders (t-shirts, hoodies, etc.) while optimizing for location, capacity, and load balancing. It uses a message-based architecture to coordinate between nodes and manage order routing.

## Core Components

### 1. Print Shop Node
Individual print shop nodes that can process orders:
```python
# Each node maintains its state and capabilities
node = PrintShopNode(
    shop=PrintShop(
        id="shop-1",
        location=Location(40.7128, -74.0060),  # NYC
        capabilities={Capability.TSHIRT, Capability.HOODIE},
        daily_capacity=100
    ),
    message_transport=message_transport
)
```

### 2. Network Discovery
Handles node discovery and cluster formation:
```python
# Nodes announce themselves to the network
await transport.publish("node.hello", {
    "node_id": "shop-1",
    "location": {"latitude": 40.7128, "longitude": -74.0060},
    "capabilities": ["TSHIRT", "HOODIE"],
    "capacity": 100
})

# Discovery service manages cluster formation
cluster_id = await discovery.handle_node_discovery(location)
```

### 3. Order Router
Routes orders to optimal nodes based on multiple criteria:
```python
# Order routing process
routing_result = await router.route_order(Order(
    id="order-123",
    customer_location=Location(40.7128, -74.0060),
    items=[
        OrderItem(product_type=Capability.TSHIRT, quantity=5)
    ]
))
```

## Message-Based Architecture

The system uses a publish/subscribe pattern for communication:

```python
# Message types
class MessageTypes:
    NODE_HELLO = "node.hello"
    NODE_BYE = "node.bye"
    ORDER_NEW = "order.new"
    ORDER_ALLOCATED = "order.allocated"
    INVENTORY_UPDATE = "inventory.update"
    CLUSTER_ANNOUNCE = "cluster.announce"
```

## Clustering and Load Balancing

The system automatically forms clusters of nearby print shops:
1. Nodes announce their presence
2. Network Discovery groups nearby nodes into clusters
3. Orders are routed to optimal clusters based on:
   - Geographic proximity
   - Available capacity
   - Required capabilities
   - Current load

## Example Flow

1. **Node Joins Network**:
```python
# Node starts up
await node.start()  # Publishes node.hello

# Discovery service handles node
cluster_id = await discovery.handle_node_discovery(node.location)
await node.join_cluster(cluster_id)
```

2. **Order Processing**:
```python
# Submit order
await transport.publish("order.new", {
    "order": {
        "id": "order-123",
        "items": [{"type": "TSHIRT", "quantity": 5}],
        "location": {"latitude": 40.7128, "longitude": -74.0060}
    }
})

# Router finds optimal node(s)
result = await router.route_order(order)

# Node processes order
if result.success:
    for node_id, items in result.node_assignments.items():
        await nodes[node_id].handle_order(order, items)
```

## Key Features

1. **Dynamic Node Discovery**
   - Nodes can join/leave network dynamically
   - Automatic cluster formation based on geography

2. **Smart Order Routing**
   - Geographic optimization
   - Load balancing across nodes
   - Support for order splitting across nodes
   - Fallback strategies for high-load scenarios

3. **Health Monitoring**
   - Periodic health checks
   - Automatic node status updates
   - Cluster optimization

## Running the System

```bash
# Start a node
export NODE_ID=shop-1
export LOCATION_LAT=40.7128
export LOCATION_LON=-74.0060
export CAPABILITIES=TSHIRT,HOODIE
export DAILY_CAPACITY=100
python -m src.main
```

## Distribution Patterns Used

1. **Publish/Subscribe**: Message-based communication between components
2. **Service Discovery**: Dynamic node discovery and cluster formation
3. **Load Balancing**: Smart order routing across nodes
4. **State Management**: Distributed state tracking across nodes
5. **Health Monitoring**: System-wide health checks and optimization