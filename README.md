# Room Access Control System

<p align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=170 alt="opal" border="0" />
</p>

## Overview

This project implements a role-based access control system for room access using OPAL (Open Policy Administration Layer) with OPA (Open Policy Agent). The system manages access permissions based on employee roles and device associations.

Key features:

* Role-based access control (RBAC) for room/device access
* Real-time policy updates via Kafka and Debezium
* Integration with external employee and device data sources
* Containerized deployment with Docker Compose

## Architecture

The system consists of the following components:

* **OPAL Server**: Manages and distributes policies and data
* **OPAL Client**: Hosts OPA instances for policy evaluation
* **Kafka**: Message broker for event streaming
* **Debezium**: CDC (Change Data Capture) connector for database events
* **Kafka Consumer**: Custom service that processes database events and updates OPAL
* **External APIs**: Endpoints that provide employee and device data

## Prerequisites

* Docker and Docker Compose
* Git
* Python 3.9+ (for local development)
* PostgreSQL (for local development)

## Installation Guide

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/room-access-control.git
cd room-access-control
```

### 2. Set up a virtual environment and install requirements

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Generate RSA key pair for OPAL authentication

You need to generate an RSA key pair for OPAL server authentication:

```bash
ssh-keygen -t rsa -b 4096 -m PEM -f "./opal_auth_key"
```

This will create two files in your current directory:

* `opal_auth_key` (private key)
* `opal_auth_key.pub` (public key)

Make sure these files have appropriate permissions:

```bash
chmod 600 opal_auth_key
chmod 644 opal_auth_key.pub
```

### 4. Generate secure master token

You'll need to generate a secure token for OPAL master authentication. Use the following command to generate a random token:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Create an environment file

Create a `.env` file in the project root with the following variables:

```
# OPAL Authentication
OPAL_AUTH_MASTER_TOKEN=your-secure-master-token
OPAL_CLIENT_TOKEN=
OPAL_DATASOURCE_TOKEN=

# Kafka Configuration (optional)
KAFKA_GROUP_ID=opal_consumer_group
```

Replace the master token value with the secure random string you generated. You'll fill in the client and datasource tokens after starting the services.

### 6. Start the services

Use this command to build and start all containers:

```bash
docker-compose up --build -d
```

This will start all the necessary services:

* Kafka (port 9092)
* Debezium (port 8083)
* OPAL Server (port 7002)
* OPAL Client (ports 7766 and 8181)
* Kafka Consumer

### 7. Generate client and datasource tokens

After the containers are running, you need to generate additional tokens for client and datasource authentication using the OPAL API.

#### Generate a client token:

```bash
curl -X POST http://localhost:7002/token \
  -H "Authorization: Bearer your-secure-master-token" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "client"
  }'
```

The response will contain a token that you should add to your `.env` file as the `OPAL_CLIENT_TOKEN` value.

#### Generate a datasource token:

```bash
curl -X POST http://localhost:7002/token \
  -H "Authorization: Bearer your-secure-master-token" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "datasource"
  }'
```

The response will contain a token that you should add to your `.env` file as the `OPAL_DATASOURCE_TOKEN` value.

You can also optionally specify a TTL (time to live) for these tokens, for example:

```bash
curl -X POST http://localhost:7002/token \
  -H "Authorization: Bearer your-secure-master-token" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "datasource",
    "ttl": "24h"
  }'
```

### 8. Restart the services to apply token changes

```bash
docker-compose down
docker-compose up -d
```

### 9. Configure Debezium for CDC (Change Data Capture)

Send a `POST` request to the Debezium API to register the PostgreSQL connector:

**URL:**

```
http://localhost:8083/connectors/
```

**Request Body (debezium-config.json):**

```json
{
  "name": "postgres-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "host.docker.internal",
    "database.port": "5432",
    "database.user": "<DB_USER>",
    "database.password": "<DB_PASSWORD>",
    "database.dbname": "<DB_NAME>",
    "database.server.name": "KPC",
    "table.include.list": "public.Employees_employees,public.Devices_devices,public.Devices_devices_roles,public.Employees_employees_devices,public.Employees_employees_roles",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_slot",
    "publication.autocreate.mode": "filtered",
    "topic.prefix": "EventNotifier"
  }
}
```

Replace `<DB_USER>`, `<DB_PASSWORD>`, and `<DB_NAME>` with your database credentials. Use `host.docker.internal` so the Debezium container can reach the local database.

**Example `curl` command:**

```bash
curl -X POST http://localhost:8083/connectors/ \
  -H "Content-Type: application/json" \
  -d @debezium-config.json
```

After this, Debezium will emit change events to Kafka, and your system will update policies automatically.

### 10. Verify the installation

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

### 11. Stopping the system

To stop all services and remove volumes (which will clear all data):

```bash
docker-compose down -v
```

## Configuration

### Policy Files

The system uses two main policy files:

* `admin_policy.rego`: Defines administrator access privileges
* `room_access_policy.rego`: Defines room access rules based on employees and devices

### External Data Sources

The system expects two external API endpoints to provide data:

* `http://host.docker.internal:8000/employees/opal-data/`
* `http://host.docker.internal:8000/devices/opal-data/`

These endpoints should return data in the format expected by OPAL.

### Kafka Topics

The system listens to the following Kafka topics:

* `EventNotifier.public.Employees_employees`
* `EventNotifier.public.Devices_devices`
* `EventNotifier.public.Devices_devices_roles`
* `EventNotifier.public.Employees_employees_roles`
* `EventNotifier.public.Employees_employees_devices`

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

   * Check if the volume is properly formatted
   * Verify network connectivity
   * Check logs: `docker-compose logs kafka`

2. **OPAL Server connectivity issues**n   - Verify correct tokens in `.env`

   * Check if the OPAL server is running
   * Check logs: `docker-compose logs opal_server`

3. **OPA policy not updating**

   * Check OPAL Client logs: `docker-compose logs opal_client`
   * Verify Git repository access
   * Check policy syntax for errors

4. **Kafka Consumer errors**

   * Check logs: `docker-compose logs kafka_consumer`
   * Verify Kafka connectivity
   * Check if OPAL server is accessible

5. **Token generation errors**

   * Make sure you're using the correct master token
   * Verify OPAL Server is running
   * Check the content type and format of your request

### Viewing Logs

```bash
# View logs for a specific service
docker-compose logs [service_name]

# Follow logs in real-time
docker-compose logs -f [service_name]
```

## Security Considerations

* Always use secure, random tokens for OPAL authentication
* Limit network access to the OPA and OPAL servers
* Regularly update all dependencies and Docker images
* Consider enabling TLS for Kafka and API endpoints
* Review access policies regularly

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## Acknowledgments

* [OPAL](https://github.com/permitio/opal) by Permit.io
* [OPA](https://www.openpolicyagent.org/) (Open Policy Agent)
* [Debezium](https://debezium.io/) for change data capture
* [Kafka](https://kafka.apache.org/) for event streaming
