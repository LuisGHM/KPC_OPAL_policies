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

### 3. Generate secure master token

You'll need to generate a secure token for OPAL master authentication. Use the following command to generate a random token:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Create an environment file

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

### 5. Start the services

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

### 6. Configure PostgreSQL for Logical Decoding

To allow Debezium to capture changes, you must set PostgreSQL’s `wal_level` to `logical` **before** registering the connector:

1. **Locate the config file** in `psql`:

   ```sql
   SHOW config_file;
   ```

   Copy the path (e.g., `C:/Program Files/PostgreSQL/17/data/postgresql.conf`).

2. **Edit** the file as Administrator in Notepad (or another editor):

   ```conf
   wal_level = logical
   ```

3. **Save** and close the file.

4. **Restart** the PostgreSQL service as Administrator in PowerShell or CMD:

   ```bash
   net stop postgresql-x64-17
   net start postgresql-x64-17
   ```

5. **Verify** in `psql`:

   ```sql
   SHOW wal_level;
   ```

   Should return `logical`.

### 7. Configure Debezium for CDC (Change Data Capture)

After PostgreSQL is set to logical decoding, send a `POST` request to the Debezium API to register the PostgreSQL connector:

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

Replace `<DB_USER>`, `<DB_PASSWORD>`, and `<DB_NAME>` with your database credentials.

**Example `curl` command:**

```bash
curl -X POST http://localhost:8083/connectors/ \
  -H "Content-Type: application/json" \
  -d @debezium-config.json
```

After this, Debezium will emit change events to Kafka, and your system will update policies automatically.

### 8. Verify the installation

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

... (rest of the document unchanged)
