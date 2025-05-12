# Room Access Control System

<p align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=170 alt="opal" border="0" />
</p>

## Overview

This project implements a role-based access control system for room access using OPAL (Open Policy Administration Layer) with OPA (Open Policy Agent). The system manages access permissions based on employee roles and device associations.

Key features:
- Role-based access control (RBAC) for room/device access
- Real-time policy updates via Kafka and Debezium
- Integration with external employee and device data sources
- Containerized deployment with Docker Compose

## Architecture

The system consists of the following components:

- **OPAL Server**: Manages and distributes policies and data
- **OPAL Client**: Hosts OPA instances for policy evaluation
- **Kafka**: Message broker for event streaming
- **Debezium**: CDC (Change Data Capture) connector for database events
- **Kafka Consumer**: Custom service that processes database events and updates OPAL
- **External APIs**: Endpoints that provide employee and device data

## Prerequisites

- Docker and Docker Compose
- Git
- Python 3.9+ (for local development)
- PostgreSQL (for local development)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/room-access-control.git
cd room-access-control
```

### 2. Create an environment file

Create a `.env` file in the project root with the following variables:

```
# OPAL Authentication
OPAL_AUTH_MASTER_TOKEN=your-secure-master-token
OPAL_CLIENT_TOKEN=your-secure-client-token
OPAL_DATASOURCE_TOKEN=your-secure-datasource-token

# Kafka Configuration (optional)
KAFKA_GROUP_ID=opal_consumer_group
```

Replace the token values with secure random strings.

### 3. Start the services

```bash
docker-compose up -d
```

This will start all the necessary services:
- Kafka (port 9092)
- Debezium (port 8083)
- OPAL Server (port 7002)
- OPAL Client (ports 7766 and 8181)
- Kafka Consumer

### 4. Verify the installation

Check if all services are running:

```bash
docker-compose ps
```

Verify OPAL Server is accessible:

```bash
curl -H "Authorization: Bearer your-secure-master-token" http://localhost:7002/healthcheck
```

Verify OPA is accessible:

```bash
curl http://localhost:8181/v1/data
```

## Configuration

### Policy Files

The system uses two main policy files:
- `admin_policy.rego`: Defines administrator access privileges
- `room_access_policy.rego`: Defines room access rules based on employees and devices

### External Data Sources

The system expects two external API endpoints to provide data:
- `http://host.docker.internal:8000/employees/opal-data/`
- `http://host.docker.internal:8000/devices/opal-data/`

These endpoints should return data in the format expected by OPAL.

### Kafka Topics

The system listens to the following Kafka topics:
- `EventNotifier.public.Employees_employees`
- `EventNotifier.public.Devices_devices`
- `EventNotifier.public.Devices_devices_roles`
- `EventNotifier.public.Employees_employees_roles`
- `EventNotifier.public.Employees_employees_devices`

## Usage

### Testing Access Control

To test if a user has access to a device/room:

```bash
curl -X POST http://localhost:8181/v1/data/access/allow -d '{
  "input": {
    "user_id": 123,
    "device_id": 456
  }
}'
```

### Administering Users and Roles

1. Add/update data through your application's database
2. The changes will be automatically captured by Debezium
3. The Kafka consumer will process these events
4. OPAL will update OPA with the new policy data

## Extending the System

### Adding New Data Types

1. Update the Kafka consumer to recognize new topics
2. Add processing logic for the new entity types
3. Update the policy files to incorporate the new data

### Modifying Policies

1. Edit the `.rego` files
2. Push changes to the Git repository
3. OPAL will detect the changes and update OPA automatically

## Troubleshooting

### Common Issues

1. **Kafka not starting**
   - Check if the volume is properly formatted
   - Verify network connectivity
   - Check logs: `docker-compose logs kafka`

2. **OPAL Server connectivity issues**
   - Verify correct tokens in `.env`
   - Check if the OPAL server is running
   - Check logs: `docker-compose logs opal_server`

3. **OPA policy not updating**
   - Check OPAL Client logs: `docker-compose logs opal_client`
   - Verify Git repository access
   - Check policy syntax for errors

4. **Kafka Consumer errors**
   - Check logs: `docker-compose logs kafka_consumer`
   - Verify Kafka connectivity
   - Check if OPAL server is accessible

### Viewing Logs

```bash
# View logs for a specific service
docker-compose logs [service_name]

# Follow logs in real-time
docker-compose logs -f [service_name]
```

## Security Considerations

- Always use secure, random tokens for OPAL authentication
- Limit network access to the OPA and OPAL servers
- Regularly update all dependencies and Docker images
- Consider enabling TLS for Kafka and API endpoints
- Review access policies regularly

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## Acknowledgments

- [OPAL](https://github.com/permitio/opal) by Permit.io
- [OPA](https://www.openpolicyagent.org/) (Open Policy Agent)
- [Debezium](https://debezium.io/) for change data capture
- [Kafka](https://kafka.apache.org/) for event streaming