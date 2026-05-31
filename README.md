# Helios Dashboard

## Running this container

### Prerequisites

- Docker
- UV (Python package manager)

### Set up

```sh
git submodule update --init --recursive
uv sync

# You may need to run this command if ruff is not available in your PATH
# export PATH="$PWD/.venv/bin:$PATH" 
make protos

docker build -t dashboard .
```

### Run

```sh
# Option 1: Default parameters
docker run -p 3000:3000 -p 8086:8086 dashboard

# Option 2: Add a volume for influxdb data
docker run -p 3000:3000 -p 8086:8086 -v /your/path/here:/root/.influxdbv2 dashboard

# Option 3: Add flags for Verbose / Standalone (Can combine with others)
docker run -p 3000:3000 -p 8086:8086 -e VERBOSE=1 -e STANDALONE=1 dashboard
```

### Access

- Grafana is on port 3000
  - `admin/admin`
- InfluxDB is on port 8086
  - `admin:admin123`