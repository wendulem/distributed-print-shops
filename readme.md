# Distributed Print Shop Network

A distributed system for coordinating print-on-demand fulfillment across a network of print shops. The system optimizes order routing based on geographic location, shop capabilities, and current capacity while providing resilience through automatic failure handling and load balancing.

## System Overview

The system consists of three main packages:

### Models Package
- Core domain objects including Orders, PrintShops, and Clusters
- Handles business logic for capacity, inventory, and status management
- Geographic location handling and distance calculations

### Network Package
- Manages the distributed network topology
- Handles shop discovery and cluster formation
- Provides inter-node communication protocols
- Monitors network health and handles failures

### Routing Package
- Intelligent order distribution across the network
- Multi-strategy routing (cluster-based, direct, split)
- Geographic and capacity-based optimization
- Load balancing and constraint handling

## Key Features

- Geographic clustering of print shops for efficient delivery
- Automatic node discovery and cluster formation
- Intelligent order routing and load balancing
- Capacity and inventory management
- Failure detection and recovery
- Split order handling for large orders
- Real-time network health monitoring

## Project Structure

```
src/
├── models/           # Core domain models
│   ├── shop.py      # Print shop and location models
│   ├── order.py     # Order and item models
│   └── cluster.py   # Cluster and metrics models
├── network/         # Network management
│   ├── discovery.py # Network formation and maintenance
│   ├── node.py     # Individual node behavior
│   └── protocol.py  # Inter-node communication
└── routing/         # Order routing
    ├── router.py    # Routing logic and strategies
    └── optimizer.py # Shop scoring and optimization

tests/
├── integration/
│   ├── test_cluster.py  # Cluster coordination tests
│   └── test_e2e.py     # End-to-end system tests
├── test_models.py      # Core model tests
├── test_discovery.py   # Network formation tests
└── test_routing.py     # Routing logic tests
```

## Testing

The test suite provides comprehensive coverage:

- Unit tests for all core components
- Integration tests for cluster coordination
- End-to-end tests for complete workflows
- Failure scenario testing
- Load and performance testing

Run tests using pytest:
```bash
pytest tests/          # Run all tests
pytest tests/test_models.py  # Run specific test file
pytest -k "test_routing"     # Run tests matching pattern
```

## Setup and Deployment

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the system:
```bash
# Start API
python api.py

# Start worker (in separate terminal)
python worker.py
```

## Deployment on Heroku

The system can be deployed on Heroku with multiple dynos:

1. Create Heroku apps:
```bash
heroku create printnode-sf  # San Francisco node
heroku create printnode-la  # Los Angeles node
```

2. Configure each node:
```bash
heroku config:set NODE_ID=sf-1 LOCATION_LAT=37.7749 LOCATION_LON=-122.4194 -a printnode-sf
```

3. Add Redis for node coordination:
```bash
heroku addons:create heroku-redis:hobby-dev
```

4. Deploy:
```bash
git push heroku-sf main
```

## Architecture Decisions

- Geographic clustering for efficient delivery
- Semi-autonomous nodes for resilience
- Multiple routing strategies for flexibility
- Protocol-based node communication
- Health monitoring and automatic recovery

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details
